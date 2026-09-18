#!/usr/bin/env python3
"""Tear down a stale wine session for a prefix, then hand off to Lutris.

    lutris-launch-game.py <wine-prefix> <flatpak-app-id> <lutris-slug> [<display-name>]

Lutris cannot do this itself. Its ProcessWatcher never signals a process named in the game's
`exclude_processes`, nor any of its own SYSTEM_PROCESSES (wineserver among them), and its comment
on iterate_children concedes it misses processes systemd reparented. A Battle.net prefix therefore
survives "stop": Agent.exe and the wineserver keep running, and with them the umu pressure-vessel
container they sit in.

That container holds an exclusive lock on the Steam runtime's `.ref`. A later launch cannot rebuild
the runtime's merged ld.so.cache while the lock is held, falls back to the LD_LIBRARY_PATH it
already had, and Proton's python then fails to resolve libffi.so.8, which the runtime ships only as
libffi.so.8.1.4 with no SONAME symlink. The game stops launching until the host reboots.

This runs on the host rather than inside the sandbox, which is the only place it works: each
`flatpak run` is its own bubblewrap instance with its own PID namespace, so a Lutris prelaunch hook
sees neither the previous launch's processes nor its own container's. The host sees every one of
them, and they carry WINEPREFIX in their environment whatever namespace they run in.

Lutris is single-instance: a second `flatpak run` hands its `lutris:rungame` to the instance already
on the bus. The instance that ran the session just torn down is shutting itself down at that moment
(a `rungame` instance quits once its game stops), and a request handed to it is lost. So the hand-off
waits for that instance, found as the sandbox ancestors of what was killed and as any instance
running this slug's `rungame`, to exit. An instance the user opened as a window does not exit, and
the wait ends at its deadline. The launcher that started the previous session is still waiting on
its Lutris, and is terminated before that Lutris is, so it does not report the teardown as a failure.

A desktop entry has no other channel, and a launch can run for minutes with nothing on screen,
so one notification is kept current through it: re-sent every few seconds for as long as
something is being waited for, its body naming what that is. It reports a launch that did not
happen with a longer banner. A clean exit gets nothing, Lutris showing its own errors in dialogs.
Every one is transient, so none reaches the message list. The icon is the one the games role
installs for the slug.

The long silence is umu fetching a Proton build: Lutris names `PROTONPATH=GE-Proton`, so a new
GE-Proton release is downloaded and unpacked on the first launch after it ships, and the
sandbox's stderr reaches no screen. The tarball lands in the sandbox's private /tmp, which the
host cannot see, but umu holds a `tmp*` directory under the flatpak's umu cache for exactly the
fetch-and-unpack span, so one that appears after the launch began and stays is the banner's cue.

The wait ends when the game has a window, which is what the banner stands in for. gamescope
gives the game a nested X server of its own, whose display the role's `gamescope-child` wrapper
exports into the game's environment, so the host reads it out of `/proc` and asks that server
what it is showing. The nested server is an Xwayland either way, so this works on an X11 host
and a Wayland one alike, unlike a query against the host display.

Lutris exits 0 whatever became of the launch, and a second instance exits 0 at once having
handed its request to the first, so a clean exit ends nothing by itself: the wait also ends when
no process of the application's sandbox is left, or at a deadline, which is reported as a
failure. A launch with no gamescope puts the game's window among the desktop's own where it
cannot be told apart, so that one ends at the prefix's wineserver instead.

One launch at a time per prefix, held under a lock in the runtime directory from the click until
the game has a window or the wait for one has ended: a second activation would otherwise tear
down what the first has just started, the teardown having no way to tell a stale session from a
sibling run's. A click while the lock is held waits for it, then reports the launch that never
happened. Once the lock is released the session belongs to whoever clicks next: one with a
window on screen is left alone as already running, and one without is torn down and relaunched.

Every decision is logged to `$XDG_STATE_HOME/lutris-launch-game/<slug>.log` (default
`~/.local/state`), since a desktop entry's stderr goes nowhere: the lock's state, every
process found and signalled, every change of the banner, what the nested display shows, and
how Lutris exited. Rotated by size.

Exits with whatever Lutris returns, or 1 for a launch that was not attempted.
"""

import contextlib
import fcntl
import hashlib
import logging
import logging.handlers
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

log = logging.getLogger("lutris-launch-game")

# Read from /proc/<pid>/environ, so the value is compared exactly rather than by path prefix: a
# sibling prefix must not be swept up with the one being launched.
PREFIX_KEYS = ("WINEPREFIX", "STEAM_COMPAT_DATA_PATH")

# Long enough for a wineserver to flush the prefix's registry, short enough that a launch does not
# feel stalled. Everything still up afterwards gets SIGKILL.
TERM_GRACE_SECONDS = 5.0
POLL_SECONDS = 0.2

# How long the previous Lutris instance gets to leave the bus. Its shutdown is a few seconds
# after its game stops; an instance with a window never does, and the launch proceeds.
LUTRIS_EXIT_SECONDS = 15.0

# How long the banner is kept up waiting for the game's window, and how often it is re-sent
# meanwhile. Long enough for a GE-Proton download on a slow link and the launcher that follows
# it; a launch with nothing on screen after this has failed some other way.
WINDOW_SECONDS = 600.0
NOTIFY_REFRESH_SECONDS = 3.0

# The nested X display gamescope gave the game, named in the environment by the wrapper in
# files/gamescope-child.sh.
GAMESCOPE_DISPLAY_KEY = b"GAMESCOPE_CHILD_XDISPLAY="

# A window at least this many pixels on both sides is one the user can see. Everything else on
# that server is 1x1 bookkeeping, and a splash screen is well above it.
WINDOW_MIN_PIXELS = 64

# `<width>x<height>+<x>+<y>`, the geometry `xwininfo -children` prints for each child.
WINDOW_GEOMETRY = re.compile(r"\b(\d+)x(\d+)[+-]\d+[+-]\d+")

XWININFO_TIMEOUT_SECONDS = 5.0

# How long a wineserver runs without a gamescope display before the launch is taken for one
# that draws on the host display, where the game's window cannot be told from the desktop's.
NO_GAMESCOPE_SECONDS = 15.0

# How long a click waits for the lock another launch holds. A launch keeps it until its window
# is up, so this is how long a second click sits behind a first one before giving up.
LOCK_WAIT_SECONDS = 30.0

# How long a process gets to leave /proc after SIGKILL. One still there is blocked in the
# kernel, its environ still readable, and must not pass for the new session's wineserver.
KILL_WAIT_SECONDS = 2.0

# umu makes its cache tmp directory on every launch and removes it within a second when no
# Proton build is needed; one that outlives this is a download or an unpack.
PROTON_INSTALL_MIN_SECONDS = 5.0

# Milliseconds each notification's banner asks for, by urgency. Every one is transient, so
# none is added to the message list: one left there stays until it is dismissed by hand, and
# a second run cannot replace it, the id reaching no further than the process that got it.
# The failure asks for the longer banner, being the one worth reading.
NOTIFY_EXPIRE_MS = {"low": "8000", "normal": "20000"}

# The log is per slug and bounded: one launch writes a few hundred lines at most.
LOG_MAX_BYTES = 1 << 20
LOG_BACKUPS = 3

# How an earlier run of this launcher is recognised on a command line, installed or not.
LAUNCHER_NAME = b"lutris-launch-game"


def setup_logging(slug):
    """Log to stderr for a terminal run, and to the state directory for a desktop-entry one."""
    formatter = logging.Formatter("%(asctime)s [%(process)d] %(levelname)s %(message)s")
    log.setLevel(logging.DEBUG)
    stderr = logging.StreamHandler()
    stderr.setFormatter(formatter)
    log.addHandler(stderr)
    state_home = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    log_dir = Path(state_home) / "lutris-launch-game"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            log_dir / f"{slug}.log", maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS
        )
    except OSError as error:
        log.warning("not logging to %s: %s", log_dir, error)
        return
    handler.setFormatter(formatter)
    log.addHandler(handler)


class Notifier:
    """One desktop notification, replaced in place as the launch moves on.

    A wait calls keep() on every poll: the banner is re-sent at NOTIFY_REFRESH_SECONDS, which
    is shorter than its expiry, so it stays on screen for as long as the wait does, and at
    once when its text changes. Each change of text is logged, each re-send is not.
    """

    def __init__(self, name, icon):
        self.name = name
        self.icon = icon
        self.notification_id = None
        self.current = None
        self.sent_at = 0.0

    def show(self, summary, body="", urgency="low"):
        if (summary, body, urgency) != self.current:
            log.info("notification: %s: %s", summary, body or "(no body)")
        self.current = (summary, body, urgency)
        self.sent_at = time.monotonic()
        argv = [
            "notify-send",
            "--print-id",
            "--app-name",
            self.name,
            "--icon",
            self.icon,
            "--urgency",
            urgency,
            "--transient",
            "--expire-time",
            NOTIFY_EXPIRE_MS.get(urgency, NOTIFY_EXPIRE_MS["low"]),
        ]
        if self.notification_id:
            argv += ["--replace-id", self.notification_id]
        try:
            result = subprocess.run([*argv, summary, body], capture_output=True, text=True, check=False)
        except OSError as error:
            log.warning("notify-send failed: %s", error)
            return
        if result.returncode == 0 and result.stdout.strip():
            self.notification_id = result.stdout.strip()
        elif result.returncode != 0:
            log.warning("notify-send exited %d: %s", result.returncode, result.stderr.strip())

    def keep(self, summary, body="", urgency="low"):
        """Show the banner now if its text changed, otherwise re-send it when it is due."""
        if (summary, body, urgency) != self.current or time.monotonic() - self.sent_at >= NOTIFY_REFRESH_SECONDS:
            self.show(summary, body, urgency)


class PrefixLock:
    """The prefix's launch lock, held from the click until the game has a window.

    One launch at a time per prefix. teardown() cannot tell a stale session from one a sibling
    run started a second ago, both carrying the prefix in their environment and neither being
    an ancestor of the other, so a second launch kills what the first has just started. A
    desktop entry gives no launch feedback and a launch takes twenty seconds to put a window
    up, which makes a second click the ordinary case rather than the exceptional one.

    Released once the launch has ended, whether the window appeared or the wait for it ran out,
    and by the kernel when this process ends, so a run that is killed or crashes leaves nothing
    to clear. The name is a digest because the lock belongs to the prefix, not the game: two
    games sharing one prefix must not launch at once either.
    """

    def __init__(self, prefix):
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        digest = hashlib.sha256(prefix.encode()).hexdigest()[:16]
        self.path = Path(runtime_dir) / f"lutris-launch-game.{digest}.lock" if runtime_dir else None
        self.handle = None

    def acquire(self, on_wait):
        """Hold the lock; False when another launch kept it for LOCK_WAIT_SECONDS."""
        if self.path is None:
            log.warning("no XDG_RUNTIME_DIR; launching without the concurrency guard")
            return True
        # Opened for append, never "w": the other launcher's handle is the same inode, and
        # truncation is a write to it while it is held.
        self.handle = self.path.open("a")
        started = time.monotonic()
        waited = False
        while True:
            try:
                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                if not waited:
                    waited = True
                    log.info("%s is held by another launch; waiting up to %.0fs", self.path, LOCK_WAIT_SECONDS)
                if time.monotonic() - started >= LOCK_WAIT_SECONDS:
                    log.warning("%s still held after %.0fs; giving up", self.path, LOCK_WAIT_SECONDS)
                    return False
                on_wait()
                time.sleep(POLL_SECONDS)
                continue
            log.info("%s acquired after %.1fs", self.path, time.monotonic() - started)
            return True

    def release(self):
        if self.handle is None:
            return
        with contextlib.suppress(OSError):
            fcntl.flock(self.handle, fcntl.LOCK_UN)
        self.handle.close()
        self.handle = None
        log.info("%s released", self.path)


def stat_fields(pid):
    """The fields of /proc/<pid>/stat after comm, which is parenthesised and may hold spaces."""
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    except OSError:
        return []


def own_pids():
    """This process and every ancestor, none of which may be signalled."""
    pids = set()
    pid = os.getpid()
    while pid > 1:
        pids.add(pid)
        fields = stat_fields(pid)
        if not fields:
            break
        pid = int(fields[1])
    return pids


def is_running(pid):
    fields = stat_fields(pid)
    # A process that has exited but not been reaped keeps its /proc entry, so the state decides.
    return bool(fields) and fields[0] != "Z"


def environ_of(pid):
    try:
        return Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    except OSError:
        # Gone between the listing and the read, or another user's.
        return []


def cmdline_of(pid):
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return b""


def comm_of(pid):
    try:
        return Path(f"/proc/{pid}/comm").read_text().strip()
    except OSError:
        return ""


def describe(pids):
    """`<pid> <comm>` for each, for the log."""
    return ", ".join(f"{pid} {comm_of(pid) or '?'}" for pid in sorted(pids)) or "none"


def prefix_pids(prefix, exclude):
    """Every process carrying the prefix."""
    wanted = {f"{key}={value}".encode() for key in PREFIX_KEYS for value in prefix}
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid in exclude:
            continue
        if wanted & set(environ_of(pid)):
            found.append(pid)
    return found


def signal_pids(pids, sig):
    for pid in pids:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            log.debug("%s %d: already gone", sig.name, pid)
        except PermissionError:
            log.warning("%s %d (%s): permission denied", sig.name, pid, comm_of(pid))


def sandbox_pids(app_id, exclude):
    """Every process of the application's sandbox, sub-sandboxes included."""
    wanted = f"FLATPAK_ID={app_id}".encode()
    return [
        int(entry.name)
        for entry in Path("/proc").iterdir()
        if entry.name.isdigit() and int(entry.name) not in exclude and wanted in environ_of(int(entry.name))
    ]


def rungame_pids(app_id, slug, exclude):
    """The processes of a Lutris instance started for this slug's `rungame`.

    Found by command line rather than by descent from the prefix, so an instance whose game is
    already gone, and which is about to quit, is still waited for.
    """
    wanted = f"lutris:rungame/{slug}".encode()
    return {pid for pid in sandbox_pids(app_id, exclude) if wanted in cmdline_of(pid)}


def ancestors_of(pids, exclude):
    """Every ancestor of the given processes, nearest first for each."""
    for pid in pids:
        ancestor = pid
        while ancestor > 1:
            fields = stat_fields(ancestor)
            if not fields:
                break
            if ancestor not in exclude:
                yield ancestor
            ancestor = int(fields[1])


def sandbox_ancestors(pids, app_id, exclude):
    """The processes inside the application's sandbox that the given ones descend from.

    The game itself runs in a sub-sandbox the portal spawned, whose ancestor is the portal; the
    launcher wrapper Lutris runs it through carries the prefix too and descends from Lutris.
    """
    wanted = f"FLATPAK_ID={app_id}".encode()
    return {pid for pid in ancestors_of(pids, exclude) if wanted in environ_of(pid)}


def launcher_ancestors(pids, exclude):
    """Earlier runs of this launcher that the given processes descend from.

    One is still in its Lutris's wait, its lock long released, and reports that Lutris as a
    failure if it sees it killed.
    """
    return {pid for pid in ancestors_of(pids, exclude) if is_launcher(pid)}


def is_launcher(pid):
    """Whether the process is a run of this script: its interpreter or its first argument names it."""
    return any(LAUNCHER_NAME in arg for arg in cmdline_of(pid).split(b"\0")[:2])


class ProtonInstallWatch:
    """Whether umu is fetching or unpacking a Proton build.

    umu holds a `tmp*` directory under the flatpak's umu cache for that span and for nothing
    longer; a crashed run leaves its own behind, so only one that appeared after the launch
    began counts, and only once it has outlived the no-op case.
    """

    def __init__(self, app_id):
        self.cache_dir = Path.home() / ".var" / "app" / app_id / "cache" / "umu"
        self.before = self.names()
        self.first_seen = {}
        log.debug("umu cache %s holds %s before the launch", self.cache_dir, sorted(self.before) or "nothing")

    def names(self):
        try:
            return {entry.name for entry in self.cache_dir.iterdir() if entry.name.startswith("tmp")}
        except OSError:
            return set()

    def in_progress(self):
        now = time.monotonic()
        current = self.names() - self.before
        for name in current - set(self.first_seen):
            log.debug("umu cache directory %s appeared", name)
        self.first_seen = {name: self.first_seen.get(name, now) for name in current}
        return any(now - seen >= PROTON_INSTALL_MIN_SECONDS for seen in self.first_seen.values())


def wait_for_exit(pids, seconds, keep=None):
    """The given processes still up after the wait, the banner kept up meanwhile."""
    deadline = time.monotonic() + seconds
    while pids and time.monotonic() < deadline:
        if keep:
            keep()
        time.sleep(POLL_SECONDS)
        pids = [pid for pid in pids if is_running(pid)]
    return pids


def teardown(prefix, app_id, slug, notifier):
    """Stop the prefix's stale session, returning what survived SIGKILL."""
    exclude = own_pids()
    pids = prefix_pids(prefix, exclude)
    log.info("processes carrying the prefix: %s", describe(pids))
    owners = sandbox_ancestors(pids, app_id, exclude) | rungame_pids(app_id, slug, exclude)
    launchers = launcher_ancestors(owners, exclude)

    if launchers:
        # Before their Lutris goes, so none is left to report the teardown as its failure.
        log.info("terminating the earlier launcher(s): %s", describe(launchers))
        signal_pids(launchers, signal.SIGTERM)

    if pids:

        def keep():
            notifier.keep(f"Launching {notifier.name}", "Closing the previous session first.")

        keep()
        log.info("SIGTERM to %d process(es)", len(pids))
        signal_pids(pids, signal.SIGTERM)
        # Poll the set already signalled rather than walking /proc again: nothing can join it,
        # and a walk reads the environ of every process on the host.
        pids = wait_for_exit(pids, TERM_GRACE_SECONDS, keep)
        if pids:
            log.info("SIGKILL to %d process(es) that ignored SIGTERM: %s", len(pids), describe(pids))
            signal_pids(pids, signal.SIGKILL)
            pids = wait_for_exit(pids, KILL_WAIT_SECONDS, keep)
            if pids:
                log.warning("still in /proc after SIGKILL: %s", describe(pids))

    if owners:
        log.info(
            "waiting up to %.0fs for the previous %s instance to exit: %s",
            LUTRIS_EXIT_SECONDS,
            app_id,
            describe(owners),
        )

        def keep_owners():
            notifier.keep(f"Launching {notifier.name}", "Waiting for the previous Lutris instance to exit.")

        left = wait_for_exit(list(owners), LUTRIS_EXIT_SECONDS, keep_owners)
        if left:
            log.info("it is still up (%s); handing the launch to it", describe(left))
        else:
            log.info("it has exited")
    return set(pids)


def gamescope_display(pids):
    """The nested X display gamescope gave the game, or None before there is one."""
    for pid in pids:
        for value in environ_of(pid):
            if value.startswith(GAMESCOPE_DISPLAY_KEY):
                return value[len(GAMESCOPE_DISPLAY_KEY) :].decode(errors="replace")
    return None


def xwininfo(display, *args):
    """What xwininfo says, or nothing when it cannot be run or the server does not answer."""
    try:
        result = subprocess.run(
            ["xwininfo", "-display", display, *args],
            capture_output=True,
            text=True,
            timeout=XWININFO_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        log.debug("xwininfo %s failed: %s", " ".join(args), error)
        return ""
    if result.returncode != 0:
        log.debug("xwininfo %s exited %d: %s", " ".join(args), result.returncode, result.stderr.strip())
    return result.stdout


def candidate_windows(display):
    """The windows on that display big enough for the user to see, each with its map state.

    The listing carries each child's geometry but not whether it is mapped, and an unmapped
    window of a usable size is ordinary (Battle.net keeps a 640x480 one), so every child that
    is large enough is then asked for its own map state.
    """
    found = []
    for line in xwininfo(display, "-root", "-children").splitlines():
        fields = line.split()
        geometry = WINDOW_GEOMETRY.search(line)
        if not fields or not fields[0].startswith("0x") or not geometry:
            continue
        width, height = int(geometry.group(1)), int(geometry.group(2))
        if min(width, height) < WINDOW_MIN_PIXELS:
            continue
        rest = line.split(None, 1)[1]
        name = rest.split('"', 2)[1] if rest.startswith('"') else ""
        viewable = "IsViewable" in xwininfo(display, "-id", fields[0])
        found.append((fields[0], name, f"{width}x{height}", "viewable" if viewable else "unmapped"))
    return found


def window_shown(windows):
    """Whether one of the candidates is on screen."""
    return any(state == "viewable" for *_, state in windows)


def session_on_screen(prefix, exclude):
    """Whether this prefix has a window up, which tells a live session from one that is ending."""
    if not shutil.which("xwininfo"):
        log.debug("no xwininfo; cannot tell whether a session is on screen")
        return False
    display = gamescope_display(prefix_pids(prefix, exclude))
    if not display:
        log.debug("no gamescope display in the prefix's processes")
        return False
    windows = candidate_windows(display)
    log.debug("display %s shows %s", display, windows or "no window of usable size")
    return window_shown(windows)


def wait_for_window(child, prefix, app_id, notifier, exclude):
    """Keep the banner current until the game has a window; False when the wait ran out.

    A non-zero exit ends it, the child having failed. A clean exit ends nothing: Lutris exits 0
    whatever became of the launch, and a second instance exits 0 at once having handed its
    request to the first. That case ends instead when no process of the sandbox is left.
    """
    watch = ProtonInstallWatch(app_id)
    can_probe = shutil.which("xwininfo") is not None
    if not can_probe:
        log.warning("no xwininfo on PATH; the wait ends at the wineserver instead of the window")
    display = None
    wine_since = None
    last_windows = None
    deadline = time.monotonic() + WINDOW_SECONDS
    while time.monotonic() < deadline:
        returncode = child.poll()
        if returncode not in (None, 0):
            log.info("flatpak run exited %d before a window appeared", returncode)
            return True
        pids = prefix_pids(prefix, exclude)
        if can_probe and display is None:
            display = gamescope_display(pids)
            if display:
                log.info("gamescope display %s found in the game's environment", display)
        if display:
            windows = candidate_windows(display)
            if windows != last_windows:
                log.info("display %s shows %s", display, windows or "no window of usable size")
                last_windows = windows
            if window_shown(windows):
                log.info("the game has a window")
                return True
        if returncode == 0 and not sandbox_pids(app_id, exclude):
            log.info("flatpak run exited 0 and nothing of %s is left", app_id)
            return True

        if not pids:
            body = "Starting Lutris."
        elif any(comm_of(pid) == "wineserver" for pid in pids):
            if wine_since is None:
                wine_since = time.monotonic()
                log.info("the prefix's wineserver is up")
            if display is None and time.monotonic() - wine_since >= NO_GAMESCOPE_SECONDS:
                log.info(
                    "no gamescope display after %.0fs of wineserver; taking the window as shown", NO_GAMESCOPE_SECONDS
                )
                return True
            body = "Waiting for the game's window."
        elif watch.in_progress():
            body = "Installing a Proton update; this takes a few minutes."
        else:
            body = "Starting the Wine session."
        notifier.keep(f"Launching {notifier.name}", body)
        # The probe runs xwininfo once per candidate window, so the poll is the banner's own.
        time.sleep(NOTIFY_REFRESH_SECONDS)
    log.warning("no window after %.0fs", WINDOW_SECONDS)
    return False


def main():
    if len(sys.argv) not in (4, 5):
        sys.exit(f"usage: {Path(sys.argv[0]).name} <wine-prefix> <flatpak-app-id> <lutris-slug> [<display-name>]")
    given, app_id, slug = sys.argv[1:4]
    name = sys.argv[4] if len(sys.argv) == 5 else slug
    setup_logging(slug)
    notifier = Notifier(name, f"lutris_{slug}")
    # umu resolves the prefix before exporting it, so a symlinked or trailing-slash path
    # matches its processes only in canonical form; the value as given still matches
    # Lutris's own.
    prefix = (str(Path(given).expanduser().resolve()), given)
    log.info("launching %s: prefix %s, %s, lutris:rungame/%s", name, prefix[0], app_id, slug)

    def on_wait():
        notifier.keep(f"Launching {name}", "Another launch is in progress; waiting for it to finish.")

    lock = PrefixLock(prefix[0])
    if not lock.acquire(on_wait):
        notifier.show(
            f"{name} did not start",
            f"Another launch has held the prefix for {LOCK_WAIT_SECONDS:.0f} seconds.",
            urgency="normal",
        )
        return 1

    try:
        # Under the lock, so a window the other launch put up while this click waited is seen.
        if session_on_screen(prefix, own_pids()):
            log.info("%s has a session on screen; leaving it alone", prefix[0])
            notifier.show(f"{name} is already running")
            return 0

        notifier.show(f"Launching {name}", "Starting Lutris.")
        survivors = set()
        try:
            survivors = teardown(prefix, app_id, slug, notifier)
        except OSError as error:
            log.warning("teardown incomplete (%s); launching anyway", error)

        # A child rather than an exec, so the exit code can be reported. Killed if the wait
        # is interrupted, or the lock would be released with the launch still in flight.
        sys.stdout.flush()
        sys.stderr.flush()
        child = subprocess.Popen(["flatpak", "run", app_id, f"lutris:rungame/{slug}"])
        log.info("started flatpak run as pid %d", child.pid)
        try:
            shown = wait_for_window(child, prefix, app_id, notifier, own_pids() | survivors)
        except BaseException:
            child.kill()
            raise
    finally:
        lock.release()

    if not shown:
        notifier.show(f"{name} did not start", "No window appeared in ten minutes.", urgency="normal")
    returncode = child.wait()
    if returncode < 0 and -returncode in (signal.SIGTERM, signal.SIGKILL):
        # A later launch's teardown, or the user's own kill: not a failure of this one.
        log.info("Lutris was terminated by %s", signal.Signals(-returncode).name)
        return 0
    log.info("Lutris exited %d", returncode)
    if returncode != 0:
        notifier.show(f"{name} did not start", f"Lutris exited with code {returncode}.", urgency="normal")
    return returncode


if __name__ == "__main__":
    sys.exit(main())
