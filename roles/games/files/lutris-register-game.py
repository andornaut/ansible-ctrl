#!/usr/bin/env python3
"""Register a Lutris game whose configuration is derived from another game's.

Reads LUTRIS_REGISTER_CONFIG, a JSON document:

    {"data_dir": "/home/user/.var/app/net.lutris.Lutris/data/lutris",
     "source_slug": "battlenet",
     "slug": "world-of-warcraft",
     "name": "World of Warcraft",
     "game": {"args": "--exec=\\"launch WoW\\""}}

The target's configuration is the source's `game`, `system` and `wine` sections, with `game`
overlaid by the `game` given, so the target shares the source's prefix, executable and runner
settings and differs only where told to. It is rewritten every run, so a runner change made to
the source in the client follows, and a change made to the target's own entry does not survive.

The pga.db row is inserted once, with only the columns a launch reads, and re-aligned with the
source's `directory`, `runner` and `platform` after that. Lutris reads the table at startup, so
a running client shows the entry after a restart. Prints one line per change on stdout and
nothing when converged, which is what the role's changed_when keys off.

Run inside the flatpak sandbox (flatpak run --command=python3), which carries PyYAML for Lutris.
"""

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import yaml

# The sections a game's configuration file holds. Lutris keys the runner section by
# runner name, and both games here run under wine.
SECTIONS = ("game", "system", "wine")


def game_row(db, slug):
    rows = db.execute("SELECT * FROM games WHERE slug = ?", (slug,)).fetchall()
    if len(rows) > 1:
        sys.exit(f"{len(rows)} Lutris games share the slug {slug!r}; expected at most one")
    return rows[0] if rows else None


def read_config(path):
    return (yaml.safe_load(path.read_text()) or {}) if path.exists() else None


def converge_config(games_dir, source, cfg):
    source_config = read_config(games_dir / f"{source['configpath']}.yml")
    if source_config is None:
        sys.exit(f"{source['configpath']}.yml, the configuration of {cfg['source_slug']!r}, is missing")
    desired = {section: dict(source_config.get(section) or {}) for section in SECTIONS}
    desired["game"].update(cfg["game"])
    path = games_dir / f"{cfg['slug']}.yml"
    if read_config(path) != desired:
        path.write_text(yaml.safe_dump(desired, default_flow_style=False))
        print(f"wrote {path}")


def converge_row(db, source, cfg):
    columns = {
        "name": cfg["name"],
        "slug": cfg["slug"],
        "platform": source["platform"],
        "runner": source["runner"],
        "directory": source["directory"],
        "installed": 1,
        "configpath": cfg["slug"],
    }
    row = game_row(db, cfg["slug"])
    if row is None:
        columns["installed_at"] = int(time.time())
        names = ", ".join(columns)
        placeholders = ", ".join("?" for _ in columns)
        db.execute(f"INSERT INTO games ({names}) VALUES ({placeholders})", tuple(columns.values()))  # noqa: S608
        print(f"registered {cfg['slug']} (id {db.execute('SELECT last_insert_rowid()').fetchone()[0]})")
        return
    changed = {name: value for name, value in columns.items() if row[name] != value}
    if changed:
        assignments = ", ".join(f"{name} = ?" for name in changed)
        db.execute(f"UPDATE games SET {assignments} WHERE id = ?", (*changed.values(), row["id"]))  # noqa: S608
        print(f"updated {cfg['slug']}: {', '.join(changed)}")


def main():
    cfg = json.loads(os.environ["LUTRIS_REGISTER_CONFIG"])
    data_dir = Path(cfg["data_dir"])
    db = sqlite3.connect(data_dir / "pga.db")
    db.row_factory = sqlite3.Row
    with db:
        source = game_row(db, cfg["source_slug"])
        if source is None:
            sys.exit(f"no Lutris game has the slug {cfg['source_slug']!r}")
        converge_config(data_dir / "games", source, cfg)
        converge_row(db, source, cfg)


if __name__ == "__main__":
    main()
