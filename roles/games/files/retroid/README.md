# Retroid Pocket Flip 2 RetroArch sync

`syncretroid` mirrors the `games` role's managed RetroArch config onto a Retroid Pocket Flip 2
(Snapdragon 865, Android + ES-DE). Ansible cannot run on the device, so the script reproduces the role's
convergence from a host that mounts the ROM library and pushes over `adb`.

The role renders [`../../templates/syncretroid.j2`](../../templates/syncretroid.j2) to
`/usr/local/bin/syncretroid` on the controller (the `retroid` tag, gated on `games_install_retroid_sync`,
which exactly one host may enable), baking in the ROM library mount and the adb serial so the command
takes no arguments. No playbook runs it: run it by hand.

It reads the role's [`../../vars/main.yml`](../../vars/main.yml) as the source of truth and applies the
Android divergences in [`profile.yml`](profile.yml). Both are read from the role directory the command
was installed from, so edits to either reach the next run on their own; only edits to the template need
`make games -- --tags retroid` re-run. Per-divergence reasoning: the "Retroid Pocket Mini / Flip 2" and
"Cores" sections of [til/docs/retro-games.md](https://github.com/andornaut/til/blob/main/docs/retro-games.md).

## What it syncs

RetroArch and ES-DE are force-stopped for the run; reopen them after.

- **`retroarch.cfg`** - sets only the keys the role owns (Android drivers, sdcard directories, handheld
  rewind buffer), removes the keys dropped for Android (mouse/lightgun, keyboard binds), leaves every
  other line alone.
- **Playlists** - regenerated with device paths and the `_libretro_android.so` core suffix; stale
  managed `.lpl` pruned. Reuses `../retroarch-generate-playlists.py`.
- **Per-core overrides/options** - `config/<library_name>/<name>.cfg` and `.opt`, with the Android diffs
  (N64 on GLideN64 HLE, Beetle PSX HW on Vulkan at 2x).
- **BIOS** - additive push from the library (only files missing or a different size; no deletes).
- **Shaders** - the preset in `profile.yml`'s `shaders` block and the files it needs, extracted from the
  libretro slang pack and pushed additively, plus a per-core `.slangp` for every core that can load it.
  See [Shaders](#shaders).
- **ES-DE emulators** - pins each system's `<alternativeEmulator>` to the core the role prefers
  (`profile.yml` `esde_cores`), so ES-DE launches our core rather than its default.
- **Thumbnails** - mirrors RetroArch's cache: deletes device thumbnails the library dropped and pushes
  only changed files. ES-DE scrapes its own media.
- **ROM library** - mirrors each system onto `ROMS/<short name>`. Hundreds of GB over USB; resumable, so
  re-run to finish an interrupted transfer, and a converged re-run pushes nothing.
- **Cores** - not synced, and cannot be. See [Gotchas](#gotchas).

## Prerequisites

- `adb` on PATH (installed by the dev role: `make dev`), the device on USB, and its adb authorisation
  granted (accept the prompt on the device; `adb devices` shows it).
- The ROM library mounted on this host (the same mount the `games` role uses).
- On the device: RetroArch, ES-DE, the standalone emulators (Dolphin, NetherSX2), the sdcard folder
  layout, and the ES-DE custom systems installed.
- **Close RetroArch on the device first.** It rewrites `retroarch.cfg` on exit (`config_save_on_exit`),
  overwriting the push.

## Run

```bash
syncretroid --dry-run

# Full sync: config plus the ROM library mirror (resumable).
syncretroid

# Everything except the BIOS and ROM mirror
syncretroid --skip-bios --skip-roms

# Against a different library, device or device profile.
syncretroid --library-dir /path/to/rom-library --serial 296b55ab
syncretroid --profile /path/to/other-device.yml
```

Flag | Description
--- | ---
`--dry-run` | print every device write, change nothing
`--library-dir` | ROM library mount (baked in at install; override to sync from elsewhere)
`--serial <id>` | pick a device when several are attached (baked in at install)
`--profile <path>` | device profile to apply (defaults to the `profile.yml` beside this README)
`--role-vars <path>` | the role data to converge from (defaults to the role's `vars/main.yml`)
`--skip-bios` | do not push the BIOS set
`--skip-roms` | do not push ROMs
`--skip-shaders` | do not fetch or push the shader files (the per-core presets are still written)
`--skip-thumbnails` | do not mirror RetroArch's thumbnail cache

## Verify on the device (once)

`syncretroid` cannot derive these from the host, and a wrong value fails silently.

**Core names.** Per-core overrides live under `config/<library_name>/`, where `<library_name>` is the
core's runtime name (not in the `.info` file, can differ per build). `profile.yml`'s `core_probe`
hardcodes the well-known names; confirm them against what RetroArch created after the cores have loaded
once. Any override directory not in that listing is ignored: fix the `library_name` and re-run.

```bash
adb shell 'sed -n "s/^rgui_config_directory = \"\(.*\)\"/\1/p" \
  /storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg'
adb shell ls "/storage/emulated/0/RetroArch/config"
```

**Pad indices.** `profile.yml`'s `controller` block binds rewind/fast-forward, but the axis/button
values are physical device indices that differ per pad, so they ship as `nul`. Bind the two hotkeys in
RetroArch (Settings > Input > Hotkeys: **Rewind** and **Fast-Forward Hold**), close it, read the
resolved values back, and copy the four into `profile.yml`.

```bash
adb shell 'grep -E "input_(rewind|hold_fast_forward)_(btn|axis)" \
  /storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg'
```

The panel refresh rate (`video_refresh_rate`, `60.000000`) is already correct for the Flip 2's single
60Hz mode. Re-derive it from "Settings > Video > Output > Estimated Screen Framerate" only for different
hardware; RetroArch derives its audio resampling ratio from it, so a mismatch is heard as drift.

## Shaders

The preset is CRT Geom Deluxe, which adds halation, phosphor persistence, raster bloom and real mask
textures to the curvature and scanlines plain `crt-geom` already has. It exists only as a slang preset,
and that decides the video driver: the Android build ships `gl` and `vulkan` only (no `glcore`) and `gl`
loads GLSL, so **vulkan is the global driver here**, and the cores whose renderer cannot follow are
pinned back to `gl` in `profile.yml`'s `core_overrides_set`.

Those pinned cores get no shader, because a slang preset under `gl` is only a load error:

Core | Driver | Why
--- | --- | ---
Mupen64Plus-Next | `gl` | GLideN64 is an OpenGL renderer and fails to load content at all under vulkan. ParaLLEl-RDP is the Vulkan path and no Adreno driver can run it.
PPSSPP | `gl` | The libretro core's Vulkan path on Android has a long run of crash reports. `gl` is what it runs on today.

Everything else, including Flycast and Beetle PSX HW (already on vulkan), gets
`config/<library_name>/<library_name>.slangp`: a one-line `#reference` to the pushed preset, so the pack
keeps its relative paths.

`syncretroid` owns those preset files, so tune the shader in `profile.yml`'s `shaders.params` rather
than by saving parameters in RetroArch, which the next sync overwrites. Keys are the `#pragma parameter`
names in `crt/shaders/geom-deluxe/geom-deluxe-params.inc`:

```yaml
shaders:
  params:
    aperture_brightboost: "0.6"   # masks are dim at 1080p on a handheld panel
    halation: "0"                 # with phosphor_amplitude 0, drops the expensive passes
```

The push is additive and carries only the files the preset opens (11 of the pack's ~5500), so installing
the full pack later with Online Updater > Update Slang Shaders is not pruned back out.

## Gotchas

- **Cores come from the in-app Core Updater.** sdcard and emulated storage are mounted `noexec`, so
  RetroArch can only `dlopen` from the app-private cores dir (`/data/user/0/<package>/cores`), which
  `adb` cannot write on a non-rooted device. Install cores with RetroArch > Online Updater > Core
  Downloader; playlists point `core_path` there. Until a core is installed, its entries show but will
  not launch.
- **`retroarch.cfg` push under `/Android/data` can be denied.** `adb push` cannot always write another
  app's scoped storage. Grant RetroArch all-files access (its config then moves to
  `/storage/emulated/0/RetroArch/`, which `syncretroid` discovers), or copy the staged cfg in with an
  on-device file manager.
- **GameCube and PS2 are not libretro playlists** (libretro Dolphin crashes on Android, LRPS2 is
  x86-only); they run in the standalone Dolphin and NetherSX2 apps through ES-DE.
- **Changing a system's ES-DE short name strands its old directories.** `mirror_roms` and
  `configure_esde_cores` iterate the current `rom_dir_names` / `esde_cores` maps, so a name no longer in
  them is never visited and never pruned. After editing a `rom_dir_names` value, remove three
  directories on the device by hand, or ES-DE keeps showing the old system alongside the new one,
  listing the same games from a copy that is never updated again:

  ```bash
  adb shell rm -rf "/storage/<uuid>/ROMS/<old>" \
                   "/storage/emulated/0/ES-DE/gamelists/<old>" \
                   "/storage/<uuid>/ES-DE/downloaded_media/<old>"
  ```

  Move `gamelists/<old>/gamelist.xml` and `downloaded_media/<old>/` to the new name first to keep the
  scraped metadata and media: ES-DE keys both by short name, `syncretroid` manages neither (it only sets
  `<alternativeEmulator>`, preserving the rest of the gamelist), and re-scraping is the only other way
  to get them back. Renaming `ROMS/<old>` too saves re-pushing the set over USB.
- **PS2 uses NetherSX2-Turnip** (`xyz.aethersx2.tturnip`) for the Turnip Adreno driver. Two device-side
  edits `syncretroid` does not manage, reverted by re-copying the custom_systems:
  - `ES-DE/custom_systems/es_find_rules.xml`: repoint the `AETHERSX2-TURNIP` entry to
    `xyz.aethersx2.tturnip/xyz.aethersx2.android.EmulationActivity`.
  - Set renderer, resolution, controls, and BIOS path by hand in the app (app-private storage; adb
    cannot port them). Seed the PS2 BIOS into the app's `bios/` from the sdcard `BIOS/pcsx2/bios/` set.
