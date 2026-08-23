#!/usr/bin/env python3
"""Report what each installed libretro core says about itself, as JSON on stdout.

    {"dolphin": {"library_name": "dolphin-emu", "valid_extensions": ["iso", "rvz", ...],
                 "block_extract": true}}

Three things only the built core knows, none of them in its .info file:

  * library_name, the name RetroArch keeps the core's override and core options under
    (config/<library_name>/). A property of the build, not the core (it has carried a version
    qualifier like "(alpha)" that upstream later dropped), so it must be asked per host;
  * valid_extensions, what the core will open;
  * block_extract, whether the core insists on being handed an archive unopened, which decides
    whether a zip is a launchable playlist entry at all: a zip extension on a block_extract core
    segfaults RetroArch.

Run inside the flatpak sandbox (flatpak run --command=python3), where RetroArch loads these cores
and the only place they all load: a core can need a library only the runtime carries (LRPS2 wants
libaio) and will not load on the host. A core that still will not load here is a broken build, so
this exits non-zero and names it rather than leaving a dud in RetroArch's core list.

Takes the cores directory as its sole argument.
"""

import ctypes
import json
import os
import sys
from pathlib import Path

SUFFIX = "_libretro.so"


class CoreInfo(ctypes.Structure):
    """retro_system_info, as retro_get_system_info() fills it in."""

    _fields_ = [
        ("library_name", ctypes.c_char_p),
        ("library_version", ctypes.c_char_p),
        ("valid_extensions", ctypes.c_char_p),
        ("need_fullpath", ctypes.c_bool),
        ("block_extract", ctypes.c_bool),
    ]


def main(cores_dir):
    cores, broken = {}, []
    for path in sorted(Path(cores_dir).glob("*" + SUFFIX)):
        try:
            # str(): ctypes wants a name, and accepting a Path is an
            # implementation detail rather than a documented one.
            library = ctypes.CDLL(str(path))
            info = CoreInfo()
            library.retro_get_system_info(ctypes.byref(info))
        except OSError as error:
            broken.append(f"{path.name}: {error}")
            continue

        extensions = (info.valid_extensions or b"").decode().split("|")
        cores[path.name[: -len(SUFFIX)]] = {
            "library_name": info.library_name.decode(),
            "valid_extensions": [extension for extension in extensions if extension],
            "block_extract": bool(info.block_extract),
        }

    # os._exit, not a return: a core's ELF destructors run when the interpreter
    # finalizes, and one that segfaults there (LRPS2 does) fails the caller after
    # the answer has already been written. Nothing here needs unwinding.
    if broken:
        sys.stderr.write("the flatpak runtime cannot load these cores:\n  " + "\n  ".join(broken) + "\n")
        sys.stderr.flush()
        os._exit(1)

    print(json.dumps(cores))
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main(sys.argv[1])
