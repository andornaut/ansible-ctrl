# Helper scripts

The four scripts that implement the `games` role's RetroArch convergence, and the one that registers a Lutris
game. The role runs four of them (`../tasks/retroarch.yml`, `../tasks/lutris.yml`); `gen-fbneo-arcade-names.py` is
run by hand only, its output committed. Each can be run by hand to debug a single stage.

**Each script's module docstring is the authoritative reference** for its full input schema, defaults,
and edge cases. This file is the operator's quick start.

| Script                            | Role                                                                                                                       | Input                                                                                   |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `retroarch-probe-cores.py`        | Reports what each installed core says about itself (`library_name`, `valid_extensions`, `block_extract`) as JSON on stdout | Cores directory, as its sole argument                                                   |
| `retroarch-generate-playlists.py` | Regenerates the `.lpl` playlists from the ROM library                                                                      | `RETROARCH_GENERATOR_CONFIG`, a JSON document                                           |
| `retroarch-fetch-thumbnails.py`   | Fills the shared thumbnail cache from [thumbnails.libretro.com](https://thumbnails.libretro.com)                           | `RETROARCH_THUMBNAILS_CONFIG`, a JSON document with `playlist_dir` and `thumbnails_dir` |
| `gen-fbneo-arcade-names.py`       | Regenerates the committed `fbneo-arcade-names.json` romset-to-title map                                                    | None. Needs network access                                                              |
| `lutris-register-game.py`         | Registers a Lutris game whose configuration is derived from another game's, in `pga.db` and `games/<slug>.yml`             | `LUTRIS_REGISTER_CONFIG`, a JSON document                                               |

- Runtime pipeline: probe -> generate -> fetch. `gen-fbneo-arcade-names.py` is a maintenance script, run by hand
  only when fbneo adds games; commit the regenerated JSON afterward.
- The generator removes the playlists of systems that have left the table, but only ones it can prove it wrote.
- Only the thumbnail fetcher writes into the ROM library tree (the shared `_Thumbnails` cache). Run it on the host
  whose mount is writable; the rest read the cache.
- `retroarch-probe-cores.py` must run **inside the flatpak sandbox**, where RetroArch loads the cores: it
  `dlopen`s each one, and a core needing a library only the runtime carries (LRPS2 wants `libaio`) will not load
  on the host. A core that will not load in the sandbox either is a broken build, so the script exits non-zero
  and names it.
- Playlist generation is also driven, against a different mount layout, by
  [`retroid/syncretroid.py`](retroid/syncretroid.py), which then mirrors the desktop's filled thumbnail cache
  over `adb` rather than fetching. The examples below are the desktop invocation.

## Paths

The examples use the paths a `--user` flatpak install of RetroArch exposes (`$HOME` is the target user's home).
Substitute your own if RetroArch lives elsewhere.

| What               | Path                                                                                             |
| ------------------ | ------------------------------------------------------------------------------------------------ |
| Config tree        | `$HOME/.var/app/org.libretro.RetroArch/config/retroarch`                                         |
| Cores              | `<config tree>/cores`                                                                            |
| Playlists          | `<config tree>/playlists`                                                                        |
| Per-core config    | `<config tree>/config`                                                                           |
| Core `.info` files | `$HOME/.local/share/flatpak/app/org.libretro.RetroArch/current/active/files/share/libretro/info` |
| ROM library        | Wherever the library is mounted (e.g. `/media/nas/games`)                                        |

## Running by hand

```bash
config="$HOME/.var/app/org.libretro.RetroArch/config/retroarch"
info="$HOME/.local/share/flatpak/app/org.libretro.RetroArch/current/active/files/share/libretro/info"

# Probe the cores
cores=$(flatpak run --command=python3 org.libretro.RetroArch - "$config/cores" < retroarch-probe-cores.py)

# Regenerate the playlists. Exits non-zero if a system declares content its core cannot launch;
# prints one line per rewritten playlist, which is what the role's changed_when keys off.
RETROARCH_GENERATOR_CONFIG=$(cat <<JSON
{
  "library_dir": "/media/nas/games",
  "playlist_dir": "$config/playlists",
  "cores_dir": "$config/cores",
  "info_dir": "$info",
  "cores": $cores,
  "systems": {"Nintendo - Game Boy": {"core": "gambatte", "extensions": ["zip"]}}
}
JSON
) ./retroarch-generate-playlists.py

# Fill the thumbnail cache. Prints one line per thumbnail written; games left with no box art
# go to stderr. Exits non-zero if the repository was unreachable (indistinguishable from a
# complete cache) or a system names a thumbnail_db the repository does not publish.
RETROARCH_THUMBNAILS_CONFIG=$(cat <<JSON
{"playlist_dir": "$config/playlists", "thumbnails_dir": "/media/nas/games/_Thumbnails"}
JSON
) ./retroarch-fetch-thumbnails.py
```

## Lutris

`lutris-register-game.py` runs inside the Lutris sandbox, which carries the PyYAML Lutris reads its own
configuration with. It prints one line per change and nothing when converged.

```bash
LUTRIS_REGISTER_CONFIG='{"data_dir": "'"$HOME"'/.var/app/net.lutris.Lutris/data/lutris",
  "source_slug": "battlenet", "slug": "world-of-warcraft", "name": "World of Warcraft",
  "game": {"args": "--exec=\"launch WoW\""}}' \
  flatpak run --command=python3 net.lutris.Lutris - < lutris-register-game.py
```
