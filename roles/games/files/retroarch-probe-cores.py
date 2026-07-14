#!/usr/bin/env python3
"""Report what each installed libretro core says about itself, as JSON on stdout.

    {"dolphin": {"library_name": "dolphin-emu", "valid_extensions": ["iso", "rvz", ...],
                 "block_extract": true}}

Three things only the built core knows, none of them in its .info file:

  * library_name, the name RetroArch keeps the core's override and core options under
    (config/<library_name>/). It is a property of the build rather than of the core: the PS2
    core reported "LRPS2 (alpha)" until upstream dropped the "(alpha)", so it cannot be
    written down in the role and has to be asked per host;
  * valid_extensions, what the core will open;
  * block_extract, whether the core insists on being handed an archive unopened, which is what
    decides whether a zip is a launchable playlist entry at all. GameCube was listed with a zip
    extension, Dolphin sets block_extract, and the entries segfaulted RetroArch.

Run inside the flatpak sandbox (flatpak run --command=python3), which is where RetroArch loads
these cores and the only place they all load: a core can need a library that only the runtime
carries (LRPS2 wants libaio) and will not load on the host at all. A core that still will not
load here is a broken build, not a stale one, so this exits non-zero and names it rather than
leaving a dud in RetroArch's core list.

Takes the cores directory as its sole argument.
"""

import ctypes
import glob
import json
import os
import sys

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
    for path in sorted(glob.glob(os.path.join(cores_dir, "*" + SUFFIX))):
        try:
            library = ctypes.CDLL(path)
            info = CoreInfo()
            library.retro_get_system_info(ctypes.byref(info))
        except OSError as error:
            broken.append("%s: %s" % (os.path.basename(path), error))
            continue

        extensions = (info.valid_extensions or b"").decode().split("|")
        cores[os.path.basename(path)[: -len(SUFFIX)]] = {
            "library_name": info.library_name.decode(),
            "valid_extensions": [extension for extension in extensions if extension],
            "block_extract": bool(info.block_extract),
        }

    if broken:
        sys.exit("the flatpak runtime cannot load these cores:\n  " + "\n  ".join(broken))
    print(json.dumps(cores))


if __name__ == "__main__":
    main(sys.argv[1])
