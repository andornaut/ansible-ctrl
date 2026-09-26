#!/usr/bin/env python3
"""Remove environment variables from every Lutris game's own configuration.

Reads LUTRIS_UNSET_ENV_CONFIG, a JSON document:

    {"config_dir": "/home/user/.var/app/net.lutris.Lutris/data/lutris",
     "names": ["DXVK_HUD"]}

A game's `system.env` overrides the one in `system.yml`, and install scripts write their own
values there (the Battle.net script sets `DXVK_HUD: compiler`), so a variable enforced in
`system.yml` only reaches a game that does not set it. Removing it from each game's
`games/<configpath>.yml` lets the `system.yml` value apply. Only the top-level `system.env` is
touched: an installer script copied into the file under another key is never read at launch.

Prints one line per rewritten file on stdout and nothing when converged, which is what the
role's changed_when keys off.

Run inside the flatpak sandbox (flatpak run --command=python3), which carries PyYAML for Lutris.
"""

import json
import os
from pathlib import Path

import yaml


def unset(config, names):
    """Return config without names in system.env, or None when none of them is set."""
    env = (config.get("system") or {}).get("env") or {}
    if not any(name in env for name in names):
        return None
    env = {key: value for key, value in env.items() if key not in names}
    system = {key: value for key, value in config["system"].items() if key != "env"}
    if env:
        system["env"] = env
    return {**config, "system": system}


def main():
    cfg = json.loads(os.environ["LUTRIS_UNSET_ENV_CONFIG"])
    games_dir = Path(cfg["config_dir"]) / "games"
    for path in sorted(games_dir.glob("*.yml")):
        config = yaml.safe_load(path.read_text()) or {}
        converged = unset(config, cfg["names"])
        if converged is None:
            continue
        # Through a temporary name, so an interrupted run leaves the old file rather than half of one.
        partial = path.with_name(path.name + ".part")
        partial.write_text(yaml.safe_dump(converged, default_flow_style=False, sort_keys=False))
        partial.replace(path)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
