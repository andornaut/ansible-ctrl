#!/usr/bin/env python3
"""Publish the time of the last real input, for a session whose compositor will not report it.

Writes two integers to /run/desktop-idle-input/stamp, once a second:

    <epoch of the last input> <epoch now>

The second is a heartbeat. A reader that finds it stale knows this died and that the first
number is frozen, which matters because a frozen number reads as a session going idle and
would blank a panel someone is sitting in front of.

This exists for niri. GNOME answers org.gnome.Mutter.IdleMonitor.GetIdletime and X11 answers
XScreenSaverQueryInfo, both of them counting input rather than policy, so an idle inhibitor
leaves them climbing. A Wayland compositor without such an interface offers only
ext-idle-notify-v1, which it gates on those same inhibitors, so anything built on it is
switched off by the one condition a backstop is for. Reading the devices is what is left.

It runs as root because the alternative is putting the session's account in the `input`
group, which would let anything running as that account read every keystroke: on Wayland,
where a client otherwise cannot, that gives away more than the backstop is worth. Nothing
here reads what was pressed, only that something was.

EV_ABS is deliberately not counted. A gamepad left with a drifting analog stick emits it
forever, and a controller abandoned on a couch beside a running game is exactly the case
this has to survive. Everything that must count still does: touchpads, touchscreens and
tablets all report a BTN_* key event on contact.
"""

import contextlib
import os
import select
import struct
import time
from pathlib import Path

DEVICE_DIR = Path("/dev/input")
SYS_INPUT_DIR = Path("/sys/class/input")
STAMP = Path("/run/desktop-idle-input/stamp")

# struct input_event on 64-bit: struct timeval (two longs), then type, code and value.
EVENT_FORMAT = "llHHi"
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)
EVENT_TYPE_INDEX = 2
# How many events to take per read. Only their type is read, so this is a buffer size.
EVENTS_PER_READ = 64

EV_KEY = 0x01
EV_REL = 0x02
COUNTED_TYPES = frozenset({EV_KEY, EV_REL})
# The same two as bits of the capability bitmask in <device>/capabilities/ev.
COUNTED_CAPABILITIES = (1 << EV_KEY) | (1 << EV_REL)

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
            if struct.unpack_from(EVENT_FORMAT, data, offset)[EVENT_TYPE_INDEX] in COUNTED_TYPES:
                counted = True


def publish(last_input: float, now: float) -> None:
    """Write the stamp by rename, so a reader never sees it half written."""
    pending = STAMP.with_suffix(".new")
    pending.write_text(f"{int(last_input)} {int(now)}\n")
    pending.replace(STAMP)


def main() -> None:
    STAMP.parent.mkdir(parents=True, exist_ok=True)
    opened: dict[Path, int] = {}
    now = time.time()
    last_input = now
    last_publish = 0.0
    last_rescan = 0.0

    while True:
        now = time.time()
        if now - last_rescan >= RESCAN_SECONDS:
            open_devices(opened)
            last_rescan = now

        by_descriptor = {descriptor: device for device, descriptor in opened.items()}
        readable, _, _ = select.select(list(by_descriptor), [], [], PUBLISH_SECONDS)
        for descriptor in readable:
            try:
                if drain(descriptor):
                    last_input = time.time()
            except OSError:
                # Unplugged mid-read. The rescan reopens it if it comes back.
                close_device(opened, by_descriptor[descriptor])

        now = time.time()
        if now - last_publish >= PUBLISH_SECONDS:
            publish(last_input, now)
            last_publish = now


if __name__ == "__main__":
    main()
