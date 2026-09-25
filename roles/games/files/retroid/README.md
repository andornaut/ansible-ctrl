# Retroid Pocket Flip 2 RetroArch sync

`syncretroid` copies the `games` role's managed RetroArch config to a Retroid Pocket Flip 2 (Snapdragon 865,
Android and ES-DE), which Ansible cannot reach. It reads [`../../vars/main.yml`](../../vars/main.yml) as the source
of truth and applies the Android differences in [`profile.yml`](profile.yml).

| Topic                                        | Where                                                                                                                                                                              |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| What it owns on the device and what not      | The module docstring of [`syncretroid.py`](syncretroid.py)                                                                                                                         |
| Flags                                        | `syncretroid --help`                                                                                                                                                               |
| Reason for each Android difference           | `profile.yml`'s inline comments, and the "Retroid Pocket Flip 2" and "Cores" sections of [til/docs/retro-games.md](https://github.com/andornaut/til/blob/main/docs/retro-games.md) |
| Values read off the device, shaders, gotchas | This file                                                                                                                                                                          |

## Prerequisites

Already installed on the device: RetroArch, ES-DE, the standalone emulators (Dolphin, ARMSX2, and NetherSX2-Turnip
as the PS2 fallback), the sdcard folder layout, and the ES-DE custom systems. The ROM library must be mounted on
this host.

| Check                                      | Done by `syncretroid`                                                                          |
| ------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| Library mount, sdcard root, both apps      | Yes, before any change. This also confirms `adb` selected the handheld                         |
| One device on adb                          | Yes: with several attached and no `--serial`, it refuses. The wrapper always passes `--serial` |
| Standalone emulators, ES-DE custom systems | No                                                                                             |

## Verify on the device (once)

`syncretroid` cannot derive these from the host, and a wrong value produces no error.

| Value        | Constraint                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Core names   | Per-core overrides live under `config/<library_name>/`. The runtime name is not in the `.info` file and can differ per build. `profile.yml`'s `core_probe` hardcodes the known names. An override directory whose name is not in the device's listing below is ignored: fix the `library_name` and re-run, which removes what the sync wrote under the old name. It removes only files whose first line is its `# Ansible managed` header, so RetroArch's own per-game overrides stay |
| Pad indices  | `profile.yml`'s `controller` block binds rewind and fast-forward as Android keycodes (L3, R3). The right-stick axes stay `nul`: this pad's are Z/RZ, which N64, PSP, DS and Dreamcast use in games. For a different pad, bind **Rewind** and **Fast-Forward Hold** in RetroArch (Settings > Input > Hotkeys), close it, and copy the resolved values into `profile.yml`                                                                                                               |
| Refresh rate | `video_refresh_rate` (`60.000000`) matches the Flip 2's single 60Hz mode. For different hardware, read "Settings > Video > Output > Estimated Screen Framerate". RetroArch derives its audio resampling ratio from it, so a wrong value is heard as audio drift                                                                                                                                                                                                                       |

Core names, compared against the directories RetroArch created after each core has loaded once:

```bash
adb shell 'sed -n "s/^rgui_config_directory = \"\(.*\)\"/\1/p" \
  /storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg'
adb shell ls "/storage/emulated/0/RetroArch/config"
```

Pad indices:

```bash
adb shell 'grep -E "input_(rewind|hold_fast_forward)_(btn|axis)" \
  /storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg'
```

## Shaders

The preset is CRT Geom Deluxe: plain `crt-geom`'s curvature and scanlines plus halation, phosphor persistence,
raster bloom and mask textures. It exists only as a slang preset. The Android build ships the `gl` and `vulkan`
drivers only (no `glcore`) and `gl` loads GLSL, so **vulkan is the global driver**. Cores whose renderer needs
OpenGL are pinned to `gl` in `profile.yml`'s `core_overrides_set` and get no shader.

| Core             | Driver | Reason                                                                                                                         |
| ---------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------ |
| Mupen64Plus-Next | `gl`   | GLideN64 is an OpenGL renderer and loads no content under vulkan. ParaLLEl-RDP is the Vulkan path and no Adreno driver runs it |
| PPSSPP           | `gl`   | The libretro core's Vulkan path crashes on Android; use `gl`                                                                   |

Every other core, Flycast and Beetle PSX HW included, gets `config/<library_name>/<library_name>.slangp`: a
`#reference` to the pushed preset plus any `shaders.params` keys, so the preset's relative paths resolve.

| Constraint            | Detail                                                                                                                                                                                                |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tune in `profile.yml` | `syncretroid` owns the `.slangp` files, so parameters saved in RetroArch are overwritten on the next sync. Keys are the `#pragma parameter` names in `crt/shaders/geom-deluxe/geom-deluxe-params.inc` |
| The push is additive  | It copies only the files the preset opens (11 of the pack's ~5500), so a full pack installed later from Online Updater > Update Slang Shaders is not pruned                                           |

```yaml
shaders:
  params:
    aperture_brightboost: "0.6" # masks are dim at 1080p on a handheld panel
    halation: "0" # with phosphor_amplitude 0, drops the expensive passes
```

## Gotchas

| Constraint                                  | Detail                                                                                                                                                                                                                                                                                                                                                                          |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cores come from the in-app Core Updater     | sdcard and emulated storage are mounted `noexec`, so RetroArch can only `dlopen` from the app-private cores directory (`/data/user/0/<package>/cores`), which `adb` cannot write on a non-rooted device. Install cores with RetroArch > Online Updater > Core Downloader. Playlists point `core_path` there; an entry whose core is not installed is listed but does not launch |
| The `retroarch.cfg` push can be denied      | `adb push` cannot always write another app's scoped storage under `/Android/data`. Grant RetroArch all-files access (its config then moves to `/storage/emulated/0/RetroArch/`, which `syncretroid` finds), or copy the staged cfg in with an on-device file manager                                                                                                            |
| Renaming an ES-DE system leaves the old one | `mirror_roms` and `configure_esde_cores` iterate the current `rom_dir_names` and `esde_cores` maps, so a name removed from them is never visited or pruned, and ES-DE lists the old system beside the new one. See [Renaming a system](#renaming-a-system)                                                                                                                      |

### Renaming a system

After changing a `rom_dir_names` value, move the scraped metadata and media to the new name first. `syncretroid`
does not manage them (it only sets `<alternativeEmulator>`), and re-scraping is the only other way to recover them.
Renaming `ROMS/<old>` as well saves re-pushing the set over USB. Then remove the three old directories:

```bash
adb shell rm -rf "/storage/<uuid>/ROMS/<old>" \
                 "/storage/emulated/0/ES-DE/gamelists/<old>" \
                 "/storage/<uuid>/ES-DE/downloaded_media/<old>"
```

## PS2 (ARMSX2)

PS2 runs on ARMSX2: `com.armsx2` is the sideloaded GitHub build, `come.nanodata.armsx2` the Play Store build.
NetherSX2-Turnip (`xyz.aethersx2.tturnip`) stays installed as the fallback. The two share no configuration, saves
or memory cards, so a title moved from one to the other has to be saved again.

`syncretroid` does not manage the following, and re-copying the custom systems reverts all of it:

| Constraint                                     | Detail                                                                                                                                                                                                                                                                                                      |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `es_systems.xml` needs the ARMSX2 command      | `ES-DE/custom_systems/es_systems.xml` replaces ES-DE's bundled `ps2` block, so it must carry an `ARMSX2 (Standalone)` command. The label pinned in `profile.yml` must match a `<command label>` in the installed `es_systems.xml`; a label that does not match stops the game launching                     |
| `es_find_rules.xml` needs the sideloaded build | `ES-DE/custom_systems/es_find_rules.xml` needs an `ARMSX2` emulator entry listing `com.armsx2/.MainActivity`. ES-DE 3.4.1's bundled rule lists only the Play package (`come.nanodata.armsx2`) and its `kr.co.iefriends.pcsx2.MainActivity` activity, so ES-DE does not find the sideloaded build without it |
| A custom find rule replaces the bundled one    | ES-DE parses the custom file first and skips an emulator name repeated in the bundled file. List the Play package's entries in the custom entry too, or they are lost                                                                                                                                       |
| NetherSX2-Turnip fallback                      | The label must match the `<command label>` in the installed `es_systems.xml` (`NetherSX2-Turnip (Standalone)` in the upstream set). Its find rule must point at the installed `xyz.aethersx2.tturnip/xyz.aethersx2.android.EmulationActivity`, not the `xyz.aethersx2.custom` fork                          |
| Set in the app by hand                         | The renderer (Vulkan) and the controls                                                                                                                                                                                                                                                                      |
| BIOS                                           | Point ARMSX2's BIOS import at the sdcard `BIOS/pcsx2/bios/` set `syncretroid` pushes. ARMSX2 validates the dumps and copies them to the data location chosen in its first-run wizard, so the sdcard copy is only the import source                                                                          |
| Adreno driver                                  | ARMSX2 loads a custom Adreno driver in the app, so it needs no separate Turnip build                                                                                                                                                                                                                        |

Check the packages, both custom files, and the resolved activity:

```bash
adb shell pm list packages | grep -E 'armsx2|aethersx2'
adb shell "grep -A 20 '<name>ps2</name>' /storage/emulated/0/ES-DE/custom_systems/es_systems.xml"
adb shell "grep -A 9 '<emulator name=\"ARMSX2\">' /storage/emulated/0/ES-DE/custom_systems/es_find_rules.xml"
adb shell "cmd package query-activities --brief -a android.intent.action.VIEW -d content://x --user 0 \
  | grep -i armsx2"
```
