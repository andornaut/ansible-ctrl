---
name: retroid-sync
description: Sync the Retroid Pocket Flip 2 handheld with roles/games/files/retroid/syncretroid.py over adb, and understand the device's storage and config layout. Use when asked to "sync it" with the handheld plugged in, when changing syncretroid.py or profile.yml, or when working on RetroArch/ES-DE config, cores, BIOS, shaders, playlists, thumbnails, or the ROM library mirror on the device.
---

# Retroid Pocket Flip 2 (games role, syncretroid)

Ansible cannot run on the device, so `syncretroid` reproduces the `games` role's convergence over adb: it reads `roles/games/vars/main.yml` as the source of truth, applies `profile.yml`, and reconciles retroarch.cfg (only the keys it owns), playlists, per-core overrides/options, shaders, BIOS, thumbnails, the ES-DE `<alternativeEmulator>` choices, and the ROM library mirror.

Everything lives in `roles/games/files/retroid/`. Read these before changing `syncretroid`:

| Source | Covers |
| --- | --- |
| [files/retroid/README.md](../../../roles/games/files/retroid/README.md) | The values that must be read off the device by hand, the shader rationale, the failure modes |
| `syncretroid.py`'s module docstring | What it owns on the device, and what it leaves alone |
| `profile.yml`'s inline comments | Each Android divergence, with the reasoning in `../til/docs/retro-games.md` |
| [roles/games/README.md](../../../roles/games/README.md#handheld-sync-retroid-pocket-flip-2) | How the `retroid` tag installs the wrapper on the controller, and when an edit needs the tag re-run |

To test an edit without the wrapper: `python3 roles/games/files/retroid/syncretroid.py --library-dir <library> --dry-run` (`--serial` is needed only when more than one device is on adb; the run refuses any device that does not have both RetroArch and ES-DE installed).

## Sync runbook (device plugged in, "sync it")

Run from the controller, where the ROM library is local and the command is on PATH.

1. `adb devices` should list the device (`games_retroid_serial` in `host_vars`) as `device`; if `unauthorized`, accept the prompt on the device.
2. Close RetroArch on the device. `syncretroid` force-stops it and ES-DE, but a manual reopen mid-run clobbers the push (`config_save_on_exit`).
3. Run it:

   ```bash
   syncretroid
   ```

   ROMs and thumbnails are mirrored by default. The ROM mirror is hundreds of GB over USB, so a first run takes hours, but it is resumable and pushes only new/changed files: re-runs are usually quick and finish an interrupted transfer. Run it in the background and report progress periodically.
4. Skip flags for a faster or narrower run: `--skip-roms`, `--skip-thumbnails` (ES-DE uses its own scraped media), `--skip-bios`, `--skip-shaders`. Preview any run with `--dry-run`.

## The device

- Retroid Pocket Flip 2, Snapdragon 865 (kona), Android 13 / SDK 33, ABI `arm64-v8a`.
- Removable sdcard: exFAT, mounted by uuid. It drifts, so `sdcard_uuid` in `profile.yml` is left empty and `discover_uuid` finds it at run time.
- Single 60.000Hz panel mode, so `video_refresh_rate: 60.000000` is correct, not a placeholder.
- Apps `syncretroid` touches: `com.retroarch.aarch64` (cfg at `/storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg`, per-core overrides at `rgui_config_directory` = `/storage/emulated/0/RetroArch/config`), `org.es_de.frontend` (the frontend the user launches; gamelists at `/storage/emulated/0/ES-DE/gamelists`), and the standalone emulators it pins as ES-DE alternatives: `org.dolphinemu.dolphinemu` (GameCube) and `xyz.aethersx2.tturnip` (NetherSX2-Turnip, PS2). Apps are installed with [Obtainium](https://github.com/ImranR98/Obtainium) from the [RJNY/Obtainium-Emulation-Pack](https://github.com/RJNY/Obtainium-Emulation-Pack) single-screen list; `syncretroid` only reconciles their config.

## Things that bite

- **Cores are never synced**: storage is mounted `noexec`, so they come from RetroArch's in-app Core Updater and playlists just point `core_path` at the app-private cores dir. That and the other device-side failure modes are in the README's "Gotchas".
- **ES-DE ROM dirs use North-America short names** (genesis, segacd, sega32xna, tg16, tg-cd, ...), not the library's No-Intro names; the `rom_dir_names` map bridges them.
- **`<alternativeEmulator>` is a second root element** in gamelist.xml (invalid single-root XML), so it is edited as text, and labels must match an ES-DE `es_systems.xml` `<command label>` (bundled, or from the installed custom_systems for PS2).
- Two values `syncretroid` cannot derive and that fail silently: core `library_name`s and the pad rewind/FF indices. See the README's "Verify on the device" section.
