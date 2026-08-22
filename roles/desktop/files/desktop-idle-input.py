#!/usr/bin/env python3
"""Publish how long it is since the last real input, for a session whose compositor will not say.

Writes two integers to /run/desktop-idle-input/stamp, once a second:

    <milliseconds since the last input> <wall clock epoch now>

The second is a heartbeat. A reader that finds it stale knows this died and that the first
number is frozen, which matters because a frozen number reads as a session going idle and
would blank a panel someone is sitting in front of. Nothing is published while there is no
device to watch, so a process that is running but blind goes stale the same way.

The idle time is measured here rather than left to whoever reads the stamp, because it is
measured on a clock that does not run while the host is suspended. A wall clock would make
a resume look like however long the machine was away, which is past any threshold worth
setting, and the panel would go dark as its user sat back down.

This exists for niri. GNOME answers org.gnome.Mutter.IdleMonitor.GetIdletime and X11 answers
XScreenSaverQueryInfo, both of them counting input rather than policy, so an idle inhibitor
leaves them climbing. A Wayland compositor without such an interface offers only
ext-idle-notify-v1, which it gates on those same inhibitors, so anything built on it is
switched off by the one condition a backstop is for. Reading the devices is what is left.

It runs as root because the alternative is putting the session's account in the `input`
group, which would let anything running as that account read every keystroke: on Wayland,
where a client otherwise cannot, that gives away more than the backstop is worth. Nothing
here reads what was pressed, only that something was.

Two kinds of event are deliberately not counted, both of them things that sit on hardware
rather than someone using it. EV_ABS, because a gamepad with a drifting analog stick emits
it forever. And a held key's autorepeat, because a book laid on a keyboard emits that just
as long. A controller or a book left on a desk beside a running game is the case this has
to survive. Everything that must count still does: touchpads, touchscreens and tablets all
report a BTN_* key event on contact.
"""

import contextlib
import os
import select
import struct
import sys
import time
from pathlib import Path

DEVICE_DIR = Path("/dev/input")
SYS_INPUT_DIR = Path("/sys/class/input")
STAMP = Path("/run/desktop-idle-input/stamp")

# struct input_event on 64-bit: struct timeval (two longs), then type, code and value.
EVENT_FORMAT = "llHHi"
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)
EVENT_TYPE_INDEX = 2
EVENT_VALUE_INDEX = 4
# How many events to take per read. Only the type and value are read, so this is a buffer size.
EVENTS_PER_READ = 64

EV_KEY = 0x01
EV_REL = 0x02
COUNTED_TYPES = frozenset({EV_KEY, EV_REL})
# The same two as bits of the capability bitmask in <device>/capabilities/ev.
COUNTED_CAPABILITIES = (1 << EV_KEY) | (1 << EV_REL)
# An EV_KEY value: 0 release, 1 press, 2 the kernel repeating a key that is still held.
KEY_AUTOREPEAT = 2

PUBLISH_SECONDS = 1.0
RESCAN_SECONDS = 5.0


def counts_as_input(device: Path) -> bool:
    """Whether the device can report a key or a relative motion, so is worth opening."""
    capabilities = SYS_INPUT_DIR / device.name / "device" / "capabilities" / "ev"
    try:
        # A bitmask in hex, low word last, wide enough to be split across words.
        mask = int(capabilities.read_text().split()[-1], 16)
    except (OSError, ValueError, IndexError):
        return False
    return bool(mask & COUNTED_CAPABILITIES)


def open_devices(opened: dict[Path, int]) -> None:
    """Open every countable device not already open, so a hotplug is picked up."""
    for device in sorted(DEVICE_DIR.glob("event*")):
        if device in opened or not counts_as_input(device):
            continue
        try:
            opened[device] = os.open(str(device), os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            continue


def close_device(opened: dict[Path, int], device: Path) -> None:
    descriptor = opened.pop(device, None)
    if descriptor is not None:
        with contextlib.suppress(OSError):
            os.close(descriptor)


def drain(descriptor: int) -> bool:
    """Read what is waiting on the device and report whether any of it counts as input."""
    counted = False
    while True:
        try:
            data = os.read(descriptor, EVENT_SIZE * EVENTS_PER_READ)
        except BlockingIOError:
            return counted
        if not data:
            return counted
        for offset in range(0, len(data) - EVENT_SIZE + 1, EVENT_SIZE):
            event = struct.unpack_from(EVENT_FORMAT, data, offset)
            if event[EVENT_TYPE_INDEX] not in COUNTED_TYPES:
                continue
            if event[EVENT_TYPE_INDEX] == EV_KEY and event[EVENT_VALUE_INDEX] == KEY_AUTOREPEAT:
                continue
            counted = True


def publish(idle_seconds: float, heartbeat: float) -> None:
    """Write the stamp by rename, so a reader never sees it half written."""
    pending = STAMP.with_suffix(".new")
    pending.write_text(f"{int(idle_seconds * 1000)} {int(heartbeat)}\n")
    pending.replace(STAMP)


def main() -> None:
    STAMP.parent.mkdir(parents=True, exist_ok=True)
    opened: dict[Path, int] = {}
    last_input = time.monotonic()
    last_publish = 0.0
    last_rescan = 0.0
    reported_blind = False

    while True:
        now = time.monotonic()
        if now - last_rescan >= RESCAN_SECONDS:
            open_devices(opened)
            last_rescan = now

        by_descriptor = {descriptor: device for device, descriptor in opened.items()}
        readable, _, _ = select.select(list(by_descriptor), [], [], PUBLISH_SECONDS)
        for descriptor in readable:
            try:
                if drain(descriptor):
                    last_input = time.monotonic()
            except OSError:
                # Unplugged mid-read. The rescan reopens it if it comes back.
                close_device(opened, by_descriptor[descriptor])

        now = time.monotonic()
        if now - last_publish < PUBLISH_SECONDS:
            continue
        last_publish = now

        if not opened:
            # Publishing here would say "alive" beside an idle time that only grows,
            # which is the one state the heartbeat exists to rule out. Saying nothing
            # lets the stamp go stale, which is how a dead reader is already handled.
            if not reported_blind:
                print("no input devices to watch, publishing nothing", file=sys.stderr)
                reported_blind = True
            continue

        if reported_blind:
            print(f"watching {len(opened)} input devices again", file=sys.stderr)
            reported_blind = False
        publish(now - last_input, time.time())


if __name__ == "__main__":
    main()
