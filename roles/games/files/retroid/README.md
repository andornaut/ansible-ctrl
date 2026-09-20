# Retroid Pocket Flip 2 RetroArch sync

`syncretroid` mirrors the `games` role's managed RetroArch config onto a Retroid Pocket Flip 2 (Snapdragon 865,
Android + ES-DE), which Ansible cannot reach. It reads the role's [`../../vars/main.yml`](../../vars/main.yml) as
the source of truth and applies the Android divergences in [`profile.yml`](profile.yml).

| Question                                             | Answer                                                                                                                                                                             |
| ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| What it owns on the device, and what it leaves alone | The module docstring of [`syncretroid.py`](syncretroid.py)                                                                                                                         |
| The flags                                            | `syncretroid --help`                                                                                                                                                               |
| Why each divergence exists                           | `profile.yml`'s inline comments, and the "Retroid Pocket Flip 2" and "Cores" sections of [til/docs/retro-games.md](https://github.com/andornaut/til/blob/main/docs/retro-games.md) |

This file covers what the code cannot show: values that must be read off the device by hand, the shader setup, and
the failure modes.

## Prerequisites

Already installed on the device: RetroArch, ES-DE, the standalone emulators (Dolphin, ARMSX2, and NetherSX2-Turnip
as the PS2 fallback), the sdcard folder layout, and the ES-DE custom systems. The ROM library must be mounted on
this host.

`syncretroid` checks the library mount, the sdcard root, and both apps before doing anything, which also confirms
`adb` selected the handheld: `--serial` matters only when more than one device is attached. It does not check the
standalone emulators or the custom systems.

## Verify on the device (once)

`syncretroid` cannot derive these from the host, and a wrong value fails silently.

**Core names.** Per-core overrides live under `config/<library_name>/`, the core's runtime name, which is not in
the `.info` file and can differ per build. `profile.yml`'s `core_probe` hardcodes the well-known names; confirm
them against what RetroArch created after the cores have loaded once. An override directory not in that listing is
ignored: fix the `library_name` and re-run.

```bash
adb shell 'sed -n "s/^rgui_config_directory = \"\(.*\)\"/\1/p" \
  /storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg'
adb shell ls "/storage/emulated/0/RetroArch/config"
```

**Pad indices.** `profile.yml`'s `controller` block binds rewind/fast-forward as Android keycodes (L3/R3); the
right-stick axes stay `nul` on purpose, this pad's being Z/RZ, which N64, PSP, DS and Dreamcast use in-game. For
a different pad, bind the two hotkeys in RetroArch (Settings > Input > Hotkeys: **Rewind** and
**Fast-Forward Hold**), close it, and copy the resolved values into `profile.yml`.

```bash
adb shell 'grep -E "input_(rewind|hold_fast_forward)_(btn|axis)" \
  /storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg'
```

**Refresh rate.** `video_refresh_rate` (`60.000000`) is correct for the Flip 2's single 60Hz mode. Re-derive it
from "Settings > Video > Output > Estimated Screen Framerate" only for different hardware; RetroArch derives its
audio resampling ratio from it, so a mismatch is heard as drift.

## Shaders

The preset is CRT Geom Deluxe, which adds halation, phosphor persistence, raster bloom and real mask textures to
the curvature and scanlines of plain `crt-geom`. It exists only as a slang preset, and that decides the video
driver: the Android build ships `gl` and `vulkan` only (no `glcore`) and `gl` loads GLSL, so **vulkan is the global
driver here**. Cores whose renderer cannot follow are pinned back to `gl` in `profile.yml`'s `core_overrides_set`
and get no shader.

| Core             | Driver | Why                                                                                                                                           |
| ---------------- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Mupen64Plus-Next | `gl`   | GLideN64 is an OpenGL renderer and fails to load content at all under vulkan. ParaLLEl-RDP is the Vulkan path and no Adreno driver can run it |
| PPSSPP           | `gl`   | The libretro core's Vulkan path on Android has a long run of crash reports. `gl` is what it runs on today                                     |

Everything else, including Flycast and Beetle PSX HW (already on vulkan), gets
`config/<library_name>/<library_name>.slangp`: a `#reference` to the pushed preset (plus any `shaders.params`
keys), so the pack keeps its relative paths.

- `syncretroid` owns those preset files, so tune the shader in `profile.yml`'s `shaders.params` rather than by
  saving parameters in RetroArch, which the next sync overwrites. Keys are the `#pragma parameter` names in
  `crt/shaders/geom-deluxe/geom-deluxe-params.inc`:

  ```yaml
  shaders:
    params:
      aperture_brightboost: "0.6" # masks are dim at 1080p on a handheld panel
      halation: "0" # with phosphor_amplitude 0, drops the expensive passes
  ```

- The push is additive and carries only the files the preset opens (11 of the pack's ~5500), so a later full pack
  from Online Updater > Update Slang Shaders is not pruned back out.

## Gotchas

- **Cores come from the in-app Core Updater.** sdcard and emulated storage are mounted `noexec`, so RetroArch can
  only `dlopen` from the app-private cores dir (`/data/user/0/<package>/cores`), which `adb` cannot write on a
  non-rooted device. Install them with RetroArch > Online Updater > Core Downloader; playlists point `core_path`
  there, and until a core is installed its entries show but will not launch.
- **`retroarch.cfg` push under `/Android/data` can be denied**, `adb push` not always being able to write another
  app's scoped storage. Grant RetroArch all-files access (its config then moves to `/storage/emulated/0/RetroArch/`,
  which `syncretroid` discovers), or copy the staged cfg in with an on-device file manager.
- **Changing a system's ES-DE short name strands its old directories.** `mirror_roms` and `configure_esde_cores`
  iterate the current `rom_dir_names` / `esde_cores` maps, so a name absent from them is never visited and never
  pruned: ES-DE keeps showing the old system alongside the new one. After editing a `rom_dir_names` value, remove
  three directories on the device by hand:

  ```bash
  adb shell rm -rf "/storage/<uuid>/ROMS/<old>" \
                   "/storage/emulated/0/ES-DE/gamelists/<old>" \
                   "/storage/<uuid>/ES-DE/downloaded_media/<old>"
  ```

  Move `gamelists/<old>/gamelist.xml` and `downloaded_media/<old>/` to the new name first to keep the scraped
  metadata and media, which `syncretroid` does not manage (it only sets `<alternativeEmulator>`) and re-scraping is
  the only other way to recover. Renaming `ROMS/<old>` too saves re-pushing the set over USB.

- **PS2 uses ARMSX2** (`com.armsx2` for the sideloaded GitHub build, `come.nanodata.armsx2` for the Play one).
  NetherSX2-Turnip (`xyz.aethersx2.tturnip`) stays installed as the fallback; the two share no configuration,
  saves or memory cards, so a title carried over has to be re-saved. Device-side work `syncretroid` does not
  manage, all of it reverted by re-copying the custom_systems:
  - The installed `ES-DE/custom_systems/es_systems.xml` must carry an `ARMSX2 (Standalone)` command for `ps2`, or
    the pinned label will not resolve and the game will not launch. Its `%EMULATOR_ARMSX2%` is resolved by ES-DE's
    own find rules (`com.armsx2/.MainActivity` matches the sideloaded build), so no `es_find_rules.xml` edit is
    needed for ARMSX2. Check both before the first launch:

    ```bash
    adb shell pm list packages | grep -E 'armsx2|aethersx2'
    adb shell "grep -A 20 '<name>ps2</name>' /storage/emulated/0/ES-DE/custom_systems/es_systems.xml"
    ```

  - Set the renderer (Vulkan) and the controls by hand in the app, and import the BIOS from the sdcard
    `BIOS/pcsx2/bios/` set that `syncretroid` already pushes: ARMSX2 validates the dumps and copies them into its
    own data location, so the sdcard copy is only the import source. It can load a custom Adreno driver, which is
    the one thing NetherSX2 needed its separate Turnip build for.
  - The NetherSX2-Turnip label the fallback needs differs between custom_systems versions
    (`AetherSX2-Turnip (Standalone)` in older copies, `NetherSX2-Turnip (Standalone)` now), and its find rule in
    older copies points at the `xyz.aethersx2.custom` fork rather than the installed
    `xyz.aethersx2.tturnip/xyz.aethersx2.android.EmulationActivity`.
