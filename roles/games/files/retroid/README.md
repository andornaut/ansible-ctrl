# Retroid Pocket Flip 2 RetroArch sync

`syncretroid` copies the `games` role's managed RetroArch config to a Retroid Pocket Flip 2 (Android and ES-DE),
which Ansible cannot reach. It reads [`../../vars/main.yml`](../../vars/main.yml) and applies the Android
differences in [`profile.yml`](profile.yml), whose comments give the reason for each. `syncretroid --help` lists the
flags, and the module docstring of [`syncretroid.py`](syncretroid.py) what it owns on the device.

## Prerequisites

Installed on the device by hand: RetroArch, ES-DE, the standalone emulators (Dolphin, ARMSX2, and NetherSX2-Turnip
as the PS2 fallback), the sdcard folder layout, and the ES-DE custom systems. The ROM library must be mounted on
this host. `syncretroid` checks the mount, the sdcard, both apps and the adb device before any change.

## Verify on the device (once)

`syncretroid` cannot derive these, and a wrong value produces no error.

| Value        | Constraint                                                                                                                                                                                                         |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Core names   | Per-core overrides live under `config/<library_name>/`, the core's runtime name, which can differ per build. `profile.yml`'s `core_probe` hardcodes them. A directory not in the device's listing below is ignored |
| Pad indices  | `profile.yml`'s `controller` block binds rewind and fast-forward to L3 and R3. For a different pad, bind **Rewind** and **Fast-Forward Hold** in RetroArch, close it, and copy the values below into `profile.yml` |
| Refresh rate | `video_refresh_rate` matches the Flip 2's 60Hz. For other hardware, read "Settings > Video > Output > Estimated Screen Framerate"                                                                                  |

```bash
# Core names: compare with the directories RetroArch created after each core has loaded once
adb shell 'sed -n "s/^rgui_config_directory = \"\(.*\)\"/\1/p" \
  /storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg'
adb shell ls "/storage/emulated/0/RetroArch/config"

# Pad indices
adb shell 'grep -E "input_(rewind|hold_fast_forward)_(btn|axis)" \
  /storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg'
```

## Shaders

The preset is CRT Geom Deluxe, slang only, so **vulkan is the global driver**. Mupen64Plus-Next and PPSSPP are
pinned to `gl` in `profile.yml`'s `core_overrides_set` and get no shader. Every other core gets
`config/<library_name>/<library_name>.slangp`.

Tune parameters in `profile.yml`, not in RetroArch: the next sync overwrites the `.slangp` files. Keys are the
`#pragma parameter` names in `crt/shaders/geom-deluxe/geom-deluxe-params.inc`.

```yaml
shaders:
  params:
    aperture_brightboost: "0.6" # masks are dim at 1080p on a handheld panel
    halation: "0" # with phosphor_amplitude 0, drops the expensive passes
```

## Gotchas

| Constraint                                  | Detail                                                                                                                                                                                                            |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cores come from the in-app Core Updater     | Storage is mounted `noexec` and `adb` cannot write the app-private cores directory. Install cores with RetroArch > Online Updater > Core Downloader. An entry whose core is missing is listed but does not launch |
| The `retroarch.cfg` push can be denied      | Grant RetroArch all-files access (`syncretroid` finds the moved config), or copy the staged cfg in with an on-device file manager                                                                                 |
| Renaming an ES-DE system leaves the old one | ES-DE lists the old system beside the new one. See [Renaming a system](#renaming-a-system)                                                                                                                        |

### Renaming a system

After changing a `rom_dir_names` value, move the scraped metadata and media to the new name first: `syncretroid`
does not manage them, and re-scraping is the only other way to recover them. Renaming `ROMS/<old>` as well saves
re-pushing the set over USB. Then remove the three old directories:

```bash
adb shell rm -rf "/storage/<uuid>/ROMS/<old>" \
                 "/storage/emulated/0/ES-DE/gamelists/<old>" \
                 "/storage/<uuid>/ES-DE/downloaded_media/<old>"
```

## PS2 (ARMSX2)

PS2 runs on ARMSX2 (`com.armsx2`, the sideloaded GitHub build; `come.nanodata.armsx2` is the Play Store build).
NetherSX2-Turnip (`xyz.aethersx2.tturnip`) is the fallback. The two share no saves or memory cards.

`syncretroid` does not manage the following, and re-copying the custom systems reverts all of it:

| Constraint                                     | Detail                                                                                                                                                                                 |
| ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `es_systems.xml` needs the ARMSX2 command      | `ES-DE/custom_systems/es_systems.xml` replaces ES-DE's `ps2` block, so it must carry an `ARMSX2 (Standalone)` command matching the label in `profile.yml`, or the game does not launch |
| `es_find_rules.xml` needs the sideloaded build | `ES-DE/custom_systems/es_find_rules.xml` needs an `ARMSX2` entry listing `com.armsx2/.MainActivity`. It replaces the bundled entry, so list the Play package's entries in it too       |
| NetherSX2-Turnip fallback                      | Its label must match `es_systems.xml`, and its find rule must name `xyz.aethersx2.tturnip/xyz.aethersx2.android.EmulationActivity`                                                     |
| Set in the app by hand                         | The renderer (Vulkan) and the controls                                                                                                                                                 |
| BIOS                                           | Point ARMSX2's BIOS import at the sdcard `BIOS/pcsx2/bios/` set `syncretroid` pushes                                                                                                   |

```bash
adb shell pm list packages | grep -E 'armsx2|aethersx2'
adb shell "grep -A 20 '<name>ps2</name>' /storage/emulated/0/ES-DE/custom_systems/es_systems.xml"
adb shell "grep -A 9 '<emulator name=\"ARMSX2\">' /storage/emulated/0/ES-DE/custom_systems/es_find_rules.xml"
adb shell "cmd package query-activities --brief -a android.intent.action.VIEW -d content://x --user 0 \
  | grep -i armsx2"
```
