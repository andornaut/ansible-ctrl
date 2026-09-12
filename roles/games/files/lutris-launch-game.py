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
waits for that instance, found as the sandbox ancestors of what was killed, to exit. An instance the
user opened as a window does not exit, and the wait ends at its deadline.

A desktop entry has no other channel, and the teardown and the wait can take twenty seconds
with nothing on screen, so one notification is kept current through the launch: it says when a
previous session is being closed first, and it reports a Lutris that exits non-zero. A clean exit
gets nothing, Lutris showing its own errors in dialogs. Every one is transient, so none reaches
the message list. The icon is the one the games role installs for the slug.

One launch at a time per prefix, held under a lock in the runtime directory: a second activation
would otherwise tear down what the first has just started, the teardown having no way to tell a
stale session from a sibling run's. A second run says so and leaves the first alone.

Exits with whatever Lutris returns. A teardown that cannot read or signal something is not fatal:
the launch is still worth attempting.
"""

import contextlib
import fcntl
import hashlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

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

# Milliseconds each notification's banner asks for, by urgency. Every one is transient, so
# none is added to the message list: one left there stays until it is dismissed by hand, and
# a second run cannot replace it, the id reaching no further than the process that got it.
# The failure asks for the longer banner, being the one worth reading.
NOTIFY_EXPIRE_MS = {"low": "8000", "normal": "20000"}


class Notifier:
    """One desktop notification, replaced in place as the launch moves on."""

    def __init__(self, name, icon):
        self.name = name
        self.icon = icon
        self.notification_id = None

    def show(self, summary, body="", urgency="low"):
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
        except OSError:
            return
        if result.returncode == 0 and result.stdout.strip():
            self.notification_id = result.stdout.strip()


@contextlib.contextmanager
def prefix_lock(prefix):
    """Hold this prefix's launch lock for the block, yielding False when another run has it.

    One launch at a time per prefix. teardown() cannot tell a stale session from one a sibling
    run started a second ago, both carrying the prefix in their environment and neither being
    an ancestor of the other, so a second launch kills what the first has just started. A
    desktop entry gives no launch feedback and a launch takes twenty seconds to put a window
    up, which makes a second click the ordinary case rather than the exceptional one.

    Held for the whole run and released by the kernel when this process ends, so a run that is
    killed or crashes leaves nothing to clear. The name is a digest because the lock belongs to
    the prefix, not the game: two games sharing one prefix must not launch at once either.
    """
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime_dir:
        print("lutris-launch-game: no XDG_RUNTIME_DIR; launching without the concurrency guard", file=sys.stderr)
        yield True
        return
    digest = hashlib.sha256(prefix.encode()).hexdigest()[:16]
    with (Path(runtime_dir) / f"lutris-launch-game.{digest}.lock").open("w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        yield True


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


def prefix_pids(prefix, exclude):
    wanted = {f"{key}={prefix}".encode() for key in PREFIX_KEYS}
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
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(pid, sig)


def sandbox_ancestors(pids, app_id, exclude):
    """The processes inside the application's sandbox that the given ones descend from.

    The game itself runs in a sub-sandbox the portal spawned, whose ancestor is the portal; the
    launcher wrapper Lutris runs it through carries the prefix too and descends from Lutris.
    """
    wanted = f"FLATPAK_ID={app_id}".encode()
    found = set()
    for pid in pids:
        ancestor = pid
        while ancestor > 1:
            fields = stat_fields(ancestor)
            if not fields:
                break
            if ancestor not in exclude and wanted in environ_of(ancestor):
                found.add(ancestor)
            ancestor = int(fields[1])
    return found


def wait_for_exit(pids, seconds):
    deadline = time.monotonic() + seconds
    while pids and time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
        pids = [pid for pid in pids if is_running(pid)]
    return pids


def teardown(prefix, app_id, notifier):
    exclude = own_pids()
    pids = prefix_pids(prefix, exclude)
    if not pids:
        return
    owners = sandbox_ancestors(pids, app_id, exclude)
    print(f"lutris-launch-game: terminating {len(pids)} stale process(es) in {prefix}")
    notifier.show(f"Launching {notifier.name}", "Closing the previous session first.")
    signal_pids(pids, signal.SIGTERM)

    # Poll the set already signalled rather than walking /proc again: nothing can join it, and a
    # walk reads the environ of every process on the host.
    deadline = time.monotonic() + TERM_GRACE_SECONDS
    while pids and time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
        pids = [pid for pid in pids if is_running(pid)]

    if pids:
        print(f"lutris-launch-game: killing {len(pids)} process(es) that ignored SIGTERM")
        signal_pids(pids, signal.SIGKILL)

    if owners:
        print(f"lutris-launch-game: waiting for the previous {app_id} instance to exit")
        if wait_for_exit(owners, LUTRIS_EXIT_SECONDS):
            print("lutris-launch-game: it is still up; handing the launch to it")


def main():
    if len(sys.argv) not in (4, 5):
        sys.exit(f"usage: {Path(sys.argv[0]).name} <wine-prefix> <flatpak-app-id> <lutris-slug> [<display-name>]")
    prefix, app_id, slug = sys.argv[1:4]
    name = sys.argv[4] if len(sys.argv) == 5 else slug
    notifier = Notifier(name, f"lutris_{slug}")

    with prefix_lock(prefix) as acquired:
        if not acquired:
            print("lutris-launch-game: another launch holds this prefix; leaving it to finish")
            notifier.show(f"{name} is already launching", "The window takes a moment to appear.")
            return 0

        notifier.show(f"Launching {name}", "The window takes a moment to appear.")
        try:
            teardown(prefix, app_id, notifier)
        except OSError as error:
            print(f"lutris-launch-game: teardown incomplete ({error}); launching anyway", file=sys.stderr)

        # A child rather than an exec, so the exit code can be reported. A second Lutris hands its
        # request to the first and returns at once, so this returns then too.
        sys.stdout.flush()
        sys.stderr.flush()
        returncode = subprocess.call(["flatpak", "run", app_id, f"lutris:rungame/{slug}"])
        if returncode != 0:
            notifier.show(f"{name} did not start", f"Lutris exited with code {returncode}.", urgency="normal")
        return returncode


if __name__ == "__main__":
    sys.exit(main())
