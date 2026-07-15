# Retroid Pocket Flip 2 RetroArch sync

Mirror the `games` role's managed RetroArch config onto a Retroid Pocket Flip 2 (Snapdragon 865,
stock Android + ES-DE). Ansible cannot run on the device, so `sync.py` reproduces the role's
convergence from a host that mounts the ROM library and pushes the result over `adb`.

This is **not** wired into any playbook. Run it by hand.

## What it does

`sync.py` reads the role's own `../../defaults/main.yml` as the source of truth and applies the
Android divergences in [`profile.yml`](profile.yml), then reconciles onto the device exactly the way
the role converges a desktop:

- **`retroarch.cfg`**: sets only the keys the role owns (drivers remapped to Android, directories
  pointed at the sdcard, rewind buffer sized for a handheld), removes the keys dropped for Android
  (mouse/lightgun, keyboard binds), and leaves every other line the device has alone.
- **playlists**: regenerated with device paths (the ES-DE short-name ROM dirs, mapped from the
  library's No-Intro names by `profile.yml`'s `rom_dir_names`) and the `_libretro_android.so` core
  suffix (reusing `../retroarch-generate-playlists.py`), with stale managed `.lpl` pruned. Each
  `core_path` points at the app-private cores dir the in-app Core Updater fills.
- **cores**: not managed here. Installed with the in-app Core Updater, not `adb` (Gotchas explain why).
- **per-core overrides/options**: `config/<library_name>/<name>.cfg` and `.opt`, with the Android
  diffs (N64 on GLideN64 HLE not ParaLLEl, Beetle PSX HW pinned to the Vulkan renderer at 2x).
- **BIOS**: additive push from the library.
- **thumbnails**: additive push, off by default (`--push-thumbnails`). ES-DE is the frontend here and
  scrapes its own media; RetroArch's thumbnail cache and the playlists above are seen only when
  browsing inside RetroArch directly.
- **ES-DE emulators**: pins each system's `<alternativeEmulator>` (in its `gamelist.xml`) to the core
  the role prefers (`profile.yml` `esde_cores`), so ES-DE launches our core rather than its default
  (e.g. Saturn on YabaSanshiro not Beetle Saturn, NES on Mesen, PSX on Beetle PSX HW).
- **ROM library** (`--roms` only): mirrors each library system onto `ROMS/<short name>`, deleting
  device games the library dropped and pushing only the files missing or a different size on the
  device. Off by default: it is hundreds of GB over USB and takes hours, but resumes if interrupted
  (just re-run), and a re-run once converged pushes nothing. Not `adb push --sync`: `--sync` compares
  mtime too, and the exFAT sdcard rounds mtimes, so already-correct files re-transfer every run.

ES-DE launches games with `%EXTRA_CONFIGFILE%` pointed at the synced `retroarch.cfg` and cores from
the app-private dir, so the managed `retroarch.cfg`, per-core overrides, BIOS, and ES-DE emulator
choices take effect on every ES-DE launch (the playlists are RetroArch-frontend only). RetroArch and
ES-DE are force-stopped for the run; reopen them after.

Divergences and the reasoning behind them: the "Retroid Pocket Mini / Flip 2" and "Cores" sections of
[`../../../../til/docs/retro-games.md`](../../../../til/docs/retro-games.md).

## Prerequisites

- `adb` on PATH (installed by the dev role: `make dev`), the device on USB, and its adb authorisation
  granted (accept the prompt on the device; `adb devices` shows it).
- The ROM library mounted on this host (the same mount the `games` role uses).
- On the device: RetroArch, ES-DE, the standalone emulators (Dolphin, NetherSX2, YabaSanshiro), the
  sdcard folder layout, and the ES-DE custom-systems already installed (see the TIL setup steps).
- **Close RetroArch on the device first.** It rewrites the whole of `retroarch.cfg` on exit
  (`config_save_on_exit`), so a running instance would overwrite what the sync just pushed.

## Run

```bash
# Preview: build the bundle and print every device write, touching nothing (works with no device).
./sync.py --library-dir /path/to/rom-library --dry-run

# Config sync: retroarch.cfg, playlists, per-core overrides, BIOS, ES-DE emulator choices (minutes).
./sync.py --library-dir /path/to/rom-library

# Config sync plus the full ROM library mirror (hours; resumable, so re-run to finish if interrupted).
./sync.py --library-dir /path/to/rom-library --roms
```

Useful flags: `--serial <id>` (pick a device when several are attached), `--skip-bios` for a faster
config-only reconcile, `--push-thumbnails` to also send RetroArch's thumbnail cache (off by default;
ES-DE uses its own media).

## Two things to verify on the device (once)

The sync cannot derive these from the desktop, and a wrong value fails silently. (A third, the panel
refresh rate, is already correct on this device; see below.)

### Verify the core names

Per-core overrides live under `rgui_config_directory` in `config/<library_name>/`, and
`<library_name>` is the core's **runtime** name, which is not in the `.info` file and can differ per
build. Stock Android RetroArch points `rgui_config_directory` at `/storage/emulated/0/RetroArch/config`
(not the app files dir). `profile.yml`'s `core_probe` hardcodes the well-known names; confirm them
against what RetroArch actually created after the cores have loaded once:

```bash
# read the config dir RetroArch is using, then list it
adb shell 'sed -n "s/^rgui_config_directory = \"\(.*\)\"/\1/p" \
  /storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg'
adb shell ls "/storage/emulated/0/RetroArch/config"
```

Any override directory `sync.py` created that does not match a name in that listing is being ignored:
fix the `library_name` in `core_probe` and re-run.

### Derive the pad indices

`profile.yml`'s `controller` block binds rewind/fast-forward on the pad, but the axis/button values are
**physical device indices** and differ per pad, so they ship as `nul` (unbound) until derived here. The
pad's autoconfig profile lives in app-private storage `adb` cannot read, so bind the two hotkeys in
RetroArch itself (Settings > Input > Hotkeys: **Rewind** and **Fast-Forward Hold**), close RetroArch,
then read the resolved values back out of `retroarch.cfg`:

```bash
adb shell 'grep -E "input_(rewind|hold_fast_forward)_(btn|axis)" \
  /storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg'
```

Copy the four values into `profile.yml`'s `controller` block and re-run.

### Set the panel refresh rate

`profile.yml`'s `settings_override.video_refresh_rate` is `60.000000`. RetroArch derives its audio
resampling ratio from this, so a value that does not match the panel is heard as audio drift. The Flip
2's panel is a single 60.000Hz mode (`adb shell dumpsys display | grep fps`), so the shipped value is
already correct; re-derive it from "Settings > Video > Output > Estimated Screen Framerate" only when
syncing to different hardware.

## Gotchas

- **Cores come from the in-app Core Updater, not this sync**: the sdcard and emulated storage are
  mounted `noexec`, so RetroArch cannot `dlopen` a core `.so` from either the sdcard or the app files
  dir. The only exec-capable location is the app-private cores dir (`/data/user/0/<package>/cores`),
  which `adb` cannot write on a non-rooted device. Install the table's cores with RetroArch > Online
  Updater > Core Downloader; the generated playlists point their `core_path` there
  (`profile.yml`'s `cores_ref`). Until a core is installed, its playlist entries show but will not
  launch.
- **`retroarch.cfg` push fails under `/Android/data`**: `adb push` cannot always write another app's
  scoped storage (it works on the Flip 2's stock RetroArch). If the discovered cfg path is under
  `/Android/data` and the push is denied, grant RetroArch all-files access (its config then lives under
  `/storage/emulated/0/RetroArch/`, which `sync.py` discovers), or copy the staged cfg in with an
  on-device file manager.
- **GameCube and PS2** are not libretro playlists here (the libretro Dolphin core crashes on Android
  and LRPS2 is x86-only); they run in the standalone Dolphin and NetherSX2 apps through ES-DE.
- **PS2 uses NetherSX2-Turnip** (`xyz.aethersx2.tturnip`, the `NetherSX2-…-Turnip` build from the
  Obtainium Emulation Pack), for the Turnip Adreno driver. Two device-side edits `sync.py` does not
  manage, so a re-copy of the GlazedBelmont custom_systems reverts them:
  - `ES-DE/custom_systems/es_find_rules.xml`: the `AETHERSX2-TURNIP` entry ships pointing at a
    different fork (`xyz.aethersx2.custom`); repoint it to
    `xyz.aethersx2.tturnip/xyz.aethersx2.android.EmulationActivity`.
  - Emulator settings (renderer, resolution, controls, BIOS path) live in app-private storage, so
    adb cannot port them from the old app; set them by hand in NetherSX2-Turnip. The PS2 BIOS is
    seeded into the app's `bios/` folder from the sdcard `BIOS/pcsx2/bios/` set.
