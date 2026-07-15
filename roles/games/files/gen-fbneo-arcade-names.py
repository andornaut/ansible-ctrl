#!/usr/bin/env python3
"""Regenerate fbneo-arcade-names.json: a romset-shortname -> full-title map for arcade games.

fbneo (and the No-Intro console library it does not share naming with) names each arcade romset by a
short MAME id (mslug.zip, kof2002.zip), so the playlist generator would otherwise label them "mslug".
This map lets it show "Metal Slug - Super Vehicle-001" instead, keeping the file on disk as mslug.zip.

Source is libretro-database's FBNeo arcade metadata, the same data RetroArch's own arcade scanner and
the libretro thumbnail repos are named from, so the titles line up with both. Each `game (` block maps
its `rom ( name X.zip )` to the block's `name "..."`. Board-id suffixes ("(NGM-2650 ~ NGH-2650)") are
kept: RetroArch's label_display_mode 3 hides them at display, exactly as it hides "(USA)" on consoles.

Run this by hand when fbneo adds games (rare); the JSON is committed so the role and sync.py read it
without a network fetch.
"""

import json
import os
import re
import urllib.request

DAT_URL = (
    "https://raw.githubusercontent.com/libretro/libretro-database/master/"
    "metadat/fbneo-split/FBNeo%20-%20Arcade%20Games.dat"
)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fbneo-arcade-names.json")

NAME_RE = re.compile(r'name\s+"([^"]*)"')
ROM_RE = re.compile(r'rom\s*\(\s*name\s+"?([^\s"]+\.zip)')


def main():
    with urllib.request.urlopen(DAT_URL) as handle:
        dat = handle.read().decode("utf-8", errors="replace")

    names = {}
    for block in dat.split("game (")[1:]:
        name = NAME_RE.search(block)
        rom = ROM_RE.search(block)
        if not (name and rom):
            continue
        stem = os.path.splitext(os.path.basename(rom.group(1)))[0]
        names[stem] = name.group(1)

    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(dict(sorted(names.items())), handle, ensure_ascii=False, indent=0)
        handle.write("\n")
    print("wrote %d names -> %s" % (len(names), OUT))


if __name__ == "__main__":
    main()
