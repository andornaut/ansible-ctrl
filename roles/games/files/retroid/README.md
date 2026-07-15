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
- **playlists**: regenerated with device paths and the `_libretro_android.so` core suffix (reusing
  `../retroarch-generate-playlists.py`), with stale managed `.lpl` pruned.
- **cores**: the arm64-v8a set the table needs, fetched from the Android buildbot; dropped cores removed.
- **per-core overrides/options**: `config/<library_name>/<name>.cfg` and `.opt`, with the Android
  diffs (N64 on GLideN64 HLE not ParaLLEl, Beetle PSX HW pinned to the Vulkan renderer at 2x).
- **BIOS + thumbnails**: additive push from the library.

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

# Real sync.
./sync.py --library-dir /path/to/rom-library
```

Useful flags: `--serial <id>` (pick a device when several are attached), `--skip-cores`,
`--skip-bios`, `--skip-thumbnails` (the two large pushes) for a config-only reconcile.

## Two things to verify on the device (once)

The sync cannot derive these from the desktop; both are called out because a wrong value fails
silently.

### Verify the core names

Per-core overrides live in `config/<library_name>/`, and `<library_name>` is the core's **runtime**
name, which is not in the `.info` file and can differ per build. `profile.yml`'s `core_probe` hardcodes
the well-known names; confirm them against what RetroArch actually created after the cores have loaded
once:

```bash
adb shell ls "/storage/emulated/0/Android/data/com.retroarch.aarch64/files/config"
```

Any override directory `sync.py` created that does not match a name in that listing is being ignored:
fix the `library_name` in `core_probe` and re-run.

### Derive the pad indices

`profile.yml`'s `controller` block binds rewind/fast-forward on the pad, but the axis/button values are
**physical device indices** and differ per pad, so they ship as `nul` (unbound) until derived here.
Read them from the pad's autoconfig profile on the device:

```bash
adb shell 'grep -E "input_(r_y_minus_axis|r_y_plus_axis|l3_btn|r3_btn)" \
  /storage/emulated/0/Android/data/com.retroarch.aarch64/files/autoconfig/android/*.cfg'
```

Map right-stick-up/down to `input_rewind_axis`/`input_hold_fast_forward_axis` and L3/R3 to
`input_rewind_btn`/`input_hold_fast_forward_btn`, set them in `profile.yml`, and re-run.

### Set the panel refresh rate

`profile.yml`'s `settings_override.video_refresh_rate` ships as a `60.000000` placeholder. RetroArch
derives its audio resampling ratio from this, so a value that does not match the panel is heard as
audio drift. Set it to what the device's "Settings > Video > Output > Estimated Screen Framerate"
reports (the Flip 2 panel is not necessarily 60Hz), then re-run.

## Gotchas

- **Cores won't load from the sdcard**: newer Android can refuse to `dlopen` an executable `.so` from
  external storage. If cores fail to load, set `device_dirs.cores` in `profile.yml` to
  `"{app_files}/cores"` and re-run.
- **`retroarch.cfg` push fails under `/Android/data`**: `adb push` cannot always write another app's
  scoped storage. If the discovered cfg path is under `/Android/data` and the push is denied, grant
  RetroArch all-files access (its config then lives under `/storage/emulated/0/RetroArch/`, which
  `sync.py` discovers), or copy the staged cfg in with an on-device file manager.
- **GameCube and PS2** are not libretro playlists here (the libretro Dolphin core crashes on Android
  and LRPS2 is x86-only); they run in the standalone Dolphin and NetherSX2 apps through ES-DE.
