# Retroid Pocket Flip 2 RetroArch sync

`syncretroid` mirrors the `games` role's managed RetroArch config onto a Retroid Pocket Flip 2 (Snapdragon 865,
Android + ES-DE), which Ansible cannot reach. It reads the role's [`../../vars/main.yml`](../../vars/main.yml) as
the source of truth and applies the Android divergences in [`profile.yml`](profile.yml).

| Question | Answer |
| --- | --- |
| What it owns on the device, and what it leaves alone | The module docstring of [`syncretroid.py`](syncretroid.py) |
| The flags | `syncretroid --help` |
| Why each divergence exists | `profile.yml`'s inline comments, and the "Retroid Pocket Mini / Flip 2" and "Cores" sections of [til/docs/retro-games.md](https://github.com/andornaut/til/blob/main/docs/retro-games.md) |

This file covers what the code cannot show: values that must be read off the device by hand, why the shader setup
is what it is, and the failure modes.

## Prerequisites

Already installed on the device: RetroArch, ES-DE, the standalone emulators (Dolphin, NetherSX2-Turnip), the
sdcard folder layout, and the ES-DE custom systems. The ROM library must be mounted on this host.

`syncretroid` checks the library mount, the sdcard root, and both apps before doing anything — the app check is
also how it confirms `adb` selected the handheld and not some other device, so `--serial` matters only when more
than one is attached. It does not check the standalone emulators or the custom systems.

## Verify on the device (once)

`syncretroid` cannot derive these from the host, and a wrong value fails silently.

**Core names.** Per-core overrides live under `config/<library_name>/`, where `<library_name>` is the core's
runtime name (not in the `.info` file, can differ per build). `profile.yml`'s `core_probe` hardcodes the
well-known names; confirm them against what RetroArch created after the cores have loaded once. Any override
directory not in that listing is ignored: fix the `library_name` and re-run.

```bash
adb shell 'sed -n "s/^rgui_config_directory = \"\(.*\)\"/\1/p" \
  /storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg'
adb shell ls "/storage/emulated/0/RetroArch/config"
```

**Pad indices.** `profile.yml`'s `controller` block binds rewind/fast-forward, but the axis/button values are
physical device indices that differ per pad, so they ship as `nul`. Bind the two hotkeys in RetroArch
(Settings > Input > Hotkeys: **Rewind** and **Fast-Forward Hold**), close it, read the resolved values back, and
copy the four into `profile.yml`.

```bash
adb shell 'grep -E "input_(rewind|hold_fast_forward)_(btn|axis)" \
  /storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg'
```

**Refresh rate.** `video_refresh_rate` (`60.000000`) is already correct for the Flip 2's single 60Hz mode.
Re-derive it from "Settings > Video > Output > Estimated Screen Framerate" only for different hardware; RetroArch
derives its audio resampling ratio from it, so a mismatch is heard as drift.

## Shaders

The preset is CRT Geom Deluxe, which adds halation, phosphor persistence, raster bloom and real mask textures to
the curvature and scanlines plain `crt-geom` already has. It exists only as a slang preset, and that decides the
video driver: the Android build ships `gl` and `vulkan` only (no `glcore`) and `gl` loads GLSL, so **vulkan is the
global driver here**. Cores whose renderer cannot follow are pinned back to `gl` in `profile.yml`'s
`core_overrides_set`, and get no shader, because a slang preset under `gl` is only a load error.

| Core | Driver | Why |
| --- | --- | --- |
| Mupen64Plus-Next | `gl` | GLideN64 is an OpenGL renderer and fails to load content at all under vulkan. ParaLLEl-RDP is the Vulkan path and no Adreno driver can run it |
| PPSSPP | `gl` | The libretro core's Vulkan path on Android has a long run of crash reports. `gl` is what it runs on today |

Everything else, including Flycast and Beetle PSX HW (already on vulkan), gets
`config/<library_name>/<library_name>.slangp`: a one-line `#reference` to the pushed preset, so the pack keeps its
relative paths.

- `syncretroid` owns those preset files, so tune the shader in `profile.yml`'s `shaders.params` rather than by
  saving parameters in RetroArch, which the next sync overwrites. Keys are the `#pragma parameter` names in
  `crt/shaders/geom-deluxe/geom-deluxe-params.inc`:

  ```yaml
  shaders:
    params:
      aperture_brightboost: "0.6"   # masks are dim at 1080p on a handheld panel
      halation: "0"                 # with phosphor_amplitude 0, drops the expensive passes
  ```

- The push is additive and carries only the files the preset opens (11 of the pack's ~5500), so installing the
  full pack later with Online Updater > Update Slang Shaders is not pruned back out.

## Gotchas

- **Cores come from the in-app Core Updater.** sdcard and emulated storage are mounted `noexec`, so RetroArch can
  only `dlopen` from the app-private cores dir (`/data/user/0/<package>/cores`), which `adb` cannot write on a
  non-rooted device. Install cores with RetroArch > Online Updater > Core Downloader; playlists point `core_path`
  there. Until a core is installed, its entries show but will not launch.
- **`retroarch.cfg` push under `/Android/data` can be denied.** `adb push` cannot always write another app's
  scoped storage. Grant RetroArch all-files access (its config then moves to `/storage/emulated/0/RetroArch/`,
  which `syncretroid` discovers), or copy the staged cfg in with an on-device file manager.
- **Changing a system's ES-DE short name strands its old directories.** `mirror_roms` and `configure_esde_cores`
  iterate the current `rom_dir_names` / `esde_cores` maps, so a name no longer in them is never visited and never
  pruned — ES-DE keeps showing the old system alongside the new one, listing the same games from a copy that is
  never updated again. After editing a `rom_dir_names` value, remove three directories on the device by hand:

  ```bash
  adb shell rm -rf "/storage/<uuid>/ROMS/<old>" \
                   "/storage/emulated/0/ES-DE/gamelists/<old>" \
                   "/storage/<uuid>/ES-DE/downloaded_media/<old>"
  ```

  Move `gamelists/<old>/gamelist.xml` and `downloaded_media/<old>/` to the new name first to keep the scraped
  metadata and media: ES-DE keys both by short name, `syncretroid` manages neither (it only sets
  `<alternativeEmulator>`, preserving the rest of the gamelist), and re-scraping is the only other way to get them
  back. Renaming `ROMS/<old>` too saves re-pushing the set over USB.
- **PS2 uses NetherSX2-Turnip** (`xyz.aethersx2.tturnip`) for the Turnip Adreno driver. Two device-side edits
  `syncretroid` does not manage, reverted by re-copying the custom_systems:
  - `ES-DE/custom_systems/es_find_rules.xml`: repoint the `AETHERSX2-TURNIP` entry to
    `xyz.aethersx2.tturnip/xyz.aethersx2.android.EmulationActivity`.
  - Set renderer, resolution, controls, and BIOS path by hand in the app (app-private storage; adb cannot port
    them). Seed the PS2 BIOS into the app's `bios/` from the sdcard `BIOS/pcsx2/bios/` set.
