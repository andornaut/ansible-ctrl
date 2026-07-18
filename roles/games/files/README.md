# RetroArch helper scripts

Four scripts that implement the `games` role's RetroArch convergence: they probe the installed cores,
generate playlists from the ROM library, fill the shared thumbnail cache, and regenerate the arcade
name map. The role runs them for you (`tasks/retroarch.yml`), but each is standalone and takes its
input from arguments, an environment variable, or a committed file, so any of them can be run by hand
to debug a single stage without an Ansible run.

Only the thumbnail fetcher writes into the ROM library tree (the shared `_Thumbnails` cache); the
other three read the library, so a host can mount it read-only. Playlist generation and thumbnail
fetching are also driven, over `adb` and against a different mount layout, by the Retroid sync in
[`retroid/`](retroid/) (which has its own [README](retroid/README.md)); the notes below cover the
desktop/host invocation.

Each script's module docstring is the authoritative reference for its full input schema and edge
cases; this file is the operator's quick start.

The runtime pipeline is probe -> generate -> fetch. `gen-fbneo-arcade-names.py` is a maintenance
script, run by hand only when fbneo adds games.

## Common paths

The examples below use the paths a `--user` flatpak install of RetroArch exposes. Substitute your own
if RetroArch lives elsewhere (`$HOME` is the target user's home):

| What | Path |
| --- | --- |
| Config tree | `$HOME/.var/app/org.libretro.RetroArch/config/retroarch` |
| Cores | `<config tree>/cores` |
| Playlists | `<config tree>/playlists` |
| Per-core config | `<config tree>/config` |
| Core `.info` files | `$HOME/.local/share/flatpak/app/org.libretro.RetroArch/current/active/files/share/libretro/info` |
| ROM library | wherever the library is mounted (e.g. `/media/nas/games`) |

## retroarch-probe-cores.py

Reports what each installed libretro core says about itself (`library_name`, `valid_extensions`,
`block_extract`) as a JSON object on stdout. `retroarch-generate-playlists.py` consumes this to
validate each system's extensions against the core that will run them.

It `dlopen`s each core and calls `retro_get_system_info()`, so it must run in the same environment
RetroArch loads the cores in: inside the flatpak sandbox, where a core that needs a library only the
runtime carries (LRPS2 wants `libaio`) will load. A core that still will not load there is a broken
build, so the script exits non-zero and names it.

Takes the cores directory as its sole argument:

```bash
flatpak run --command=python3 org.libretro.RetroArch - \
  "$HOME/.var/app/org.libretro.RetroArch/config/retroarch/cores" \
  < retroarch-probe-cores.py
```

Output:

```json
{"gambatte": {"library_name": "Gambatte", "valid_extensions": ["gb", "gbc", "dmg"], "block_extract": false}}
```

## retroarch-generate-playlists.py

Regenerates the playlists (`.lpl`) from the ROM library, keeping the ROM-directory-to-core mapping in
the role instead of in RetroArch's in-app content scanner. It validates every system against its
core (exiting non-zero if a system declares content its core cannot launch), writes a playlist only
when its content changed (printing one line per rewrite so `changed_when` can key off stdout), and
removes the playlists of systems that have left the table (only ones it can prove it wrote).

Configured entirely through the `RETROARCH_GENERATOR_CONFIG` environment variable, a JSON document.
Required keys:

| Key | Meaning |
| --- | --- |
| `library_dir` | ROM library root to scan (read-only) |
| `playlist_dir` | where `.lpl` files are written |
| `cores_dir` | cores directory, used to build each `core_path` |
| `info_dir` | core `.info` files, read for display names and extensions |
| `cores` | the `retroarch-probe-cores.py` output |
| `systems` | `{"<system dir>": {"core": "<core>", "extensions": ["zip", ...]}}` |

Optional keys (arcade labels, and rewriting paths for a device the generator does not itself mount)
are documented in the module docstring. Run it after probing the cores:

```bash
cores=$(flatpak run --command=python3 org.libretro.RetroArch - \
  "$HOME/.var/app/org.libretro.RetroArch/config/retroarch/cores" < retroarch-probe-cores.py)

RETROARCH_GENERATOR_CONFIG=$(cat <<JSON
{
  "library_dir": "/media/nas/games",
  "playlist_dir": "$HOME/.var/app/org.libretro.RetroArch/config/retroarch/playlists",
  "cores_dir": "$HOME/.var/app/org.libretro.RetroArch/config/retroarch/cores",
  "info_dir": "$HOME/.local/share/flatpak/app/org.libretro.RetroArch/current/active/files/share/libretro/info",
  "cores": $cores,
  "systems": {"Nintendo - Game Boy": {"core": "gambatte", "extensions": ["zip"]}}
}
JSON
) ./retroarch-generate-playlists.py
```

## retroarch-fetch-thumbnails.py

Fills the shared thumbnail cache from [thumbnails.libretro.com](https://thumbnails.libretro.com) for
every entry in the generated playlists, so a game has box art before anyone browses to it (RetroArch's
own on-demand downloader fetches only what is scrolled past). It reads the playlists rather than the
systems table, matches each label to the repository's No-Intro name (falling back to the base game's
art for a translation, fix, or homebrew re-release, and to the cart itself for Pico-8), prints one line
per thumbnail written, and lists games left with no box art on stderr.

Run it on the host whose mount is writable (the one that fills the cache); the rest read it. It exits
non-zero only if the repository could not be reached, since an unreachable server is indistinguishable
from a complete cache.

Configured through the `RETROARCH_THUMBNAILS_CONFIG` environment variable:

| Key | Meaning |
| --- | --- |
| `playlist_dir` | playlists to read labels from |
| `thumbnails_dir` | thumbnail cache to fill |

```bash
RETROARCH_THUMBNAILS_CONFIG=$(cat <<JSON
{
  "playlist_dir": "$HOME/.var/app/org.libretro.RetroArch/config/retroarch/playlists",
  "thumbnails_dir": "/media/nas/games/_Thumbnails"
}
JSON
) ./retroarch-fetch-thumbnails.py
```

## gen-fbneo-arcade-names.py

Regenerates `fbneo-arcade-names.json`, a romset-shortname-to-full-title map so the playlist generator
can label `mslug.zip` as "Metal Slug - Super Vehicle-001" instead of "mslug". It downloads
libretro-database's FBNeo arcade `.dat` and writes the JSON beside itself. The JSON is committed, so
the role and the Retroid sync read it without a network fetch.

Run it by hand when fbneo adds games (rare); it takes no arguments and needs network access:

```bash
./gen-fbneo-arcade-names.py
```

Commit the regenerated `fbneo-arcade-names.json` afterward.
