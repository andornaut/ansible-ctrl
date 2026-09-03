#!/usr/bin/env python3
"""Print the wine prefix of a Lutris game, or nothing where it has none.

Reads LUTRIS_PREFIX_CONFIG, a JSON document:

    {"config_dir": "/home/user/.var/app/net.lutris.Lutris/data/lutris",
     "data_dir": "/home/user/.var/app/net.lutris.Lutris/data/lutris",
     "slug": "battlenet"}

The two directories are the pair lutris-register-game.py takes and mean the same thing here:
`config_dir` holds `games/<configpath>.yml` and `data_dir` holds `pga.db`.

pga.db is asked first because a game's configuration file is not always named after its slug.
Lutris names it once, at install, and a second install of the same game gets a configpath of its
own (`battlenet-standard-1783482319`), so reading `games/<slug>.yml` finds nothing and a caller
that fell back to a derived path would not know it had.

An absent database, an unregistered slug and a game with no prefix all print an empty line and
exit 0: a prefix that is not there is the caller's decision to make, not an error.

Run inside the flatpak sandbox (flatpak run --command=python3), which carries PyYAML for Lutris.
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

import yaml


def configpath(db_path, slug):
    if not db_path.exists():
        return None
    db = sqlite3.connect(db_path)
    rows = db.execute("SELECT configpath FROM games WHERE slug = ?", (slug,)).fetchall()
    if len(rows) > 1:
        sys.exit(f"{len(rows)} Lutris games share the slug {slug!r}; expected at most one")
    return rows[0][0] if rows else None


def main():
    cfg = json.loads(os.environ["LUTRIS_PREFIX_CONFIG"])
    name = configpath(Path(cfg["data_dir"]) / "pga.db", cfg["slug"])
    if name is None:
        print()
        return
    path = Path(cfg["config_dir"]) / "games" / f"{name}.yml"
    config = (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}
    print((config.get("game") or {}).get("prefix") or "")


if __name__ == "__main__":
    main()
