#!/usr/bin/env python3
"""Tear down a stale wine session for a prefix, then hand off to Lutris.

    lutris-launch-game.py <wine-prefix> <flatpak-app-id> <lutris-slug>

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

Exits with whatever the exec'd Lutris returns. A teardown that cannot read or signal something is
not fatal: the launch is still worth attempting.
"""

import contextlib
import os
import signal
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


def teardown(prefix):
    exclude = own_pids()
    pids = prefix_pids(prefix, exclude)
    if not pids:
        return
    print(f"lutris-launch-game: terminating {len(pids)} stale process(es) in {prefix}")
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


def main():
    if len(sys.argv) != 4:
        sys.exit(f"usage: {Path(sys.argv[0]).name} <wine-prefix> <flatpak-app-id> <lutris-slug>")
    prefix, app_id, slug = sys.argv[1:]

    try:
        teardown(prefix)
    except OSError as error:
        print(f"lutris-launch-game: teardown incomplete ({error}); launching anyway", file=sys.stderr)

    os.execvp("flatpak", ["flatpak", "run", app_id, f"lutris:rungame/{slug}"])


if __name__ == "__main__":
    main()
