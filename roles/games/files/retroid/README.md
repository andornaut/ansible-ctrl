# Retroid Pocket Flip 2 RetroArch sync

`sync.py` mirrors the `games` role's managed RetroArch config onto a Retroid Pocket Flip 2 (Snapdragon
865, Android + ES-DE). Ansible cannot run on the device, so the script reproduces the role's
convergence from a host that mounts the ROM library and pushes over `adb`. Not wired into any playbook:
run it by hand.

It reads the role's [`../../defaults/main.yml`](../../defaults/main.yml) as the source of truth and
applies the Android divergences in [`profile.yml`](profile.yml).

## What it syncs

- **`retroarch.cfg`** - sets only the keys the role owns (Android drivers, sdcard directories, handheld
  rewind buffer), removes the keys dropped for Android (mouse/lightgun, keyboard binds), leaves every
  other line alone.
- **Playlists** - regenerated with device paths and the `_libretro_android.so` core suffix; stale
  managed `.lpl` pruned. Reuses `../retroarch-generate-playlists.py`.
- **Per-core overrides/options** - `config/<library_name>/<name>.cfg` and `.opt`, with the Android
  diffs (N64 on GLideN64 HLE, Beetle PSX HW on Vulkan at 2x).
- **BIOS** - additive push from the library (only files missing or a different size; no deletes).
- **ES-DE emulators** - pins each system's `<alternativeEmulator>` to the core the role prefers
  (`profile.yml` `esde_cores`), so ES-DE launches our core rather than its default.
- **Thumbnails** - mirrors RetroArch's cache (skip with `--skip-thumbnails`): deletes device thumbnails
  the library dropped and pushes only changed files; ES-DE scrapes its own media.
- **ROM library** - mirrors each system onto `ROMS/<short name>` (skip with `--skip-roms`). Hundreds of
  GB over USB; resumable, so re-run to finish an interrupted transfer, and a converged re-run pushes
  nothing.
- **Cores** - not synced; storage is mounted `noexec`. Install with RetroArch's in-app Core Updater
  (see [Gotchas](#gotchas)).

RetroArch and ES-DE are force-stopped for the run; reopen them after. Divergences and their reasoning:
the "Retroid Pocket Mini / Flip 2" and "Cores" sections of
[`retro-games.md`](../../../../../til/docs/retro-games.md).

## Prerequisites

- `adb` on PATH (installed by the dev role: `make dev`), the device on USB, and its adb authorisation
  granted (accept the prompt on the device; `adb devices` shows it).
- The ROM library mounted on this host (the same mount the `games` role uses).
- On the device: RetroArch, ES-DE, the standalone emulators (Dolphin, NetherSX2), the sdcard folder
  layout, and the ES-DE custom systems installed (see the TIL setup steps).
- **Close RetroArch on the device first.** It rewrites `retroarch.cfg` on exit (`config_save_on_exit`),
  overwriting the push.

## Run

```bash
./sync.py --library-dir /path/to/rom-library --dry-run

# Full sync: config plus the ROM library mirror (resumable).
./sync.py --library-dir /path/to/rom-library

# Everything except the BIOS and ROM mirror
./sync.py --library-dir /path/to/rom-library --skip-bios --skip-roms

# Pick a specific device when several are attached.
./sync.py --library-dir /media/nas/games/ --serial 296b55ab
```

Flag | Description
--- | ---
`--dry-run` | print every device write, change nothing
`--library-dir` | ROM library mount (required)
`--serial <id>` | pick a device when several are attached
`--skip-bios` | do not push the BIOS set
`--skip-roms` | do not push ROMs
`--skip-thumbnails` | do not mirror RetroArch's thumbnail cache

## Verify on the device (once)

`sync.py` cannot derive these from the host, and a wrong value fails silently.

### Core names

Per-core overrides live under `config/<library_name>/`, where `<library_name>` is the core's runtime
name (not in the `.info` file, can differ per build). `profile.yml`'s `core_probe` hardcodes the
well-known names; confirm them against what RetroArch created after the cores have loaded once:

```bash
adb shell 'sed -n "s/^rgui_config_directory = \"\(.*\)\"/\1/p" \
  /storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg'
adb shell ls "/storage/emulated/0/RetroArch/config"
```

Any override directory not in that listing is ignored: fix the `library_name` in `core_probe` and re-run.

### Pad indices

`profile.yml`'s `controller` block binds rewind/fast-forward, but the axis/button values are physical
device indices that differ per pad, so they ship as `nul`. Bind the two hotkeys in RetroArch (Settings
> Input > Hotkeys: **Rewind** and **Fast-Forward Hold**), close it, then read the resolved values back:

```bash
adb shell 'grep -E "input_(rewind|hold_fast_forward)_(btn|axis)" \
  /storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg'
```

Copy the four values into `profile.yml`'s `controller` block and re-run.

The panel refresh rate (`video_refresh_rate`, `60.000000`) is already correct for the Flip 2's single
60Hz mode. Re-derive it from "Settings > Video > Output > Estimated Screen Framerate" only for different
hardware; RetroArch derives its audio resampling ratio from it, so a mismatch is heard as drift.

## Gotchas

- **Cores come from the in-app Core Updater.** sdcard and emulated storage are mounted `noexec`, so
  RetroArch can only `dlopen` from the app-private cores dir (`/data/user/0/<package>/cores`), which
  `adb` cannot write on a non-rooted device. Install cores with RetroArch > Online Updater > Core
  Downloader; playlists point `core_path` there. Until a core is installed, its entries show but will
  not launch.
- **`retroarch.cfg` push under `/Android/data` can be denied.** `adb push` cannot always write another
  app's scoped storage. Grant RetroArch all-files access (its config then moves to
  `/storage/emulated/0/RetroArch/`, which `sync.py` discovers), or copy the staged cfg in with an
  on-device file manager.
- **GameCube and PS2 are not libretro playlists** (libretro Dolphin crashes on Android, LRPS2 is
  x86-only); they run in the standalone Dolphin and NetherSX2 apps through ES-DE.
- **PS2 uses NetherSX2-Turnip** (`xyz.aethersx2.tturnip`) for the Turnip Adreno driver. Two device-side
  edits `sync.py` does not manage, reverted by re-copying the custom_systems:
  - `ES-DE/custom_systems/es_find_rules.xml`: repoint the `AETHERSX2-TURNIP` entry to
    `xyz.aethersx2.tturnip/xyz.aethersx2.android.EmulationActivity`.
  - Set renderer, resolution, controls, and BIOS path by hand in the app (app-private storage; adb
    cannot port them). Seed the PS2 BIOS into the app's `bios/` from the sdcard `BIOS/pcsx2/bios/` set.
