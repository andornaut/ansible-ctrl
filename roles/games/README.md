# ansible-role-games

Installs gaming apt packages and flatpaks on Ubuntu, and configures RetroArch against the ROM library.

## Usage

```bash
make games
make games -- --tags flatpak
make games -- --tags retroarch
```

## Tags

| Tag | Description |
| --- | --- |
| apt | Native gaming packages |
| bedrock | Minecraft Bedrock launcher (BedrockOnLinux) from its release flatpak bundle |
| flatpak | Flatpak runtime, flathub remote, applications, extensions, and overrides |
| heroic | Heroic install path and the store token-refresh timer |
| lutris | Lutris default install path |
| retroarch | Libretro cores, BIOS, settings, per-core overrides, playlists, and thumbnails |
| retroid | `syncretroid`, the handheld sync command, installed on the controller |

## Variables

Host-settable knobs are in [defaults/main.yml](./defaults/main.yml):

| Variable | Purpose |
| --- | --- |
| `games_user` | Account flatpaks are installed for (`--user`, never root). Defaults to `primary_user` |
| `games_flatpak_apps` | Flatpak applications to install |
| `games_cursor_theme` | Cursor theme for those flatpaks, which cannot see the host's |
| `games_heroic_dir` | Heroic's game installs and wine prefixes: granted to its sandbox, and written into its `config.json` |
| `games_heroic_token_refresh_interval` | How often the `--user` timer exercises the Epic and GOG OAuth refresh tokens |
| `games_lutris_dir` | Lutris's game installs, written into its `system.yml` |
| `games_retroarch_controller` | The gamepad this host has, naming a key of `games_retroarch_controllers`. No default |
| `games_retroarch_video_refresh_rate` | This host's panel refresh rate. No default |
| `games_retroarch_extra_settings` | Per-host `retroarch.cfg` additions, combined over the required settings |
| `games_install_retroid_sync` | Install `syncretroid` on the controller. Off by default |
| `games_retroid_library_dir` | Where the controller mounts the ROM library, baked into `syncretroid`. No default |
| `games_retroid_serial` | The handheld's adb serial (`adb devices`), baked into `syncretroid`. No default |

`games_retroarch_library_dir` is the ROM library mount. It is site data, so it has no default and is not in
`defaults/`: `host_vars/` must set it.

Everything else is in [vars/main.yml](./vars/main.yml), where role vars outrank `host_vars` and so cannot be set
per host: the canonical RetroArch data (`games_retroarch_systems`, `games_retroarch_required_settings`,
`games_retroarch_core_overrides`, `games_retroarch_core_options`, `games_retroarch_controllers`), the paths derived
from the library and config directories, the upstream pins, the flatpak sandbox grants, and the fact-derived
values. `syncretroid` reads that file directly and resolves no inventory, so a `host_vars` override of any of it
would reach the desktops and silently not the handheld. Override the default a value derives from, not the derived
value.

### Per-host settings

Three values have no default and are asserted by the play. Each is site data or hardware the role cannot see,
where a guessed value would fail silently.

| Setting | Why |
| --- | --- |
| `games_retroarch_library_dir` | Where the host mounts the ROM library. The tag also asserts the library is mounted: an unmounted share looks exactly like an empty one. |
| `games_retroarch_controller` | RetroArch's `input_*_btn` and `input_*_axis` are *physical* device indices, not RetroPad IDs, so a wrong value binds a different button rather than no-oping. |
| `games_retroarch_video_refresh_rate` | RetroArch derives the audio resampling ratio from it, so its 60.0 default mistimes every core on a high-refresh panel, heard as drift. "Estimate Screen Refresh Rate" in the menu reports it. |

Read a new pad's indices out of its autoconfig profile and add an entry to `games_retroarch_controllers`:

```bash
flatpak run --command=grep org.libretro.RetroArch -E '^input_(r_y_minus_axis|r_y_plus_axis|l3_btn|r3_btn)' \
  "/app/share/libretro/autoconfig/udev/Microsoft_X-Box_Series_XS_pad.cfg"
```

`vrr_runloop_enable` is the one optional per-host setting, turned on in `games_retroarch_extra_settings` for a VRR
panel (which also wants VRR enabled outside RetroArch: a compositor setting under Wayland, `Option
"VariableRefresh"` in `xorg.conf.d` under X11, where it conflicts with `TearFree`). It cannot combine with the
other video-to-audio sync methods (vsync, a swap interval above 1, black frame insertion), and the play asserts
those preconditions. On a fixed-refresh panel leave it off and use BFI instead.

## Notes

- The role has no dependencies: it installs `flatpak` and adds the flathub remote for `games_user` itself, so it
  runs standalone on a host that has never had the [desktop](../desktop/) role applied.
- Ansible replaces dict variables rather than merging them, so a `host_vars/` override has to restate the whole
  value. `games_retroarch_extra_settings` exists to avoid that for the one dict a host has reason to add to; the
  rest are in `vars/` and are not host-settable, so add to the role instead.

## RetroArch

**Close RetroArch before running the play.** It rewrites `retroarch.cfg` and its core options on exit
(`config_save_on_exit`), so a running instance overwrites whatever the play enforced. The `retroarch` tag asserts
it is not running.

What the role owns, and the constraints that shape it:

- **`retroarch.cfg`, key by key.** The file holds thousands of keys; the role owns only those in
  `games_retroarch_required_settings`. Settings changed in the app persist, and the managed keys snap back.
- **The cores directory.** Libretro cores are not packaged for apt or flatpak, so they come from the same nightly
  buildbot the in-app Core Updater uses. Every run installs the current build (nightlies only, so there is nothing
  to pin, and a refetch repairs a core the flatpak runtime can no longer load after a runtime upgrade), and a core
  no system runs is removed so it cannot linger in "Load Core". Each is dlopened inside the sandbox to read its
  reported name, which doubles as the load check. The set is the desktop (x64) column of the
  [til notes](https://github.com/andornaut/til/blob/main/docs/retro-games.md#cores).
- **The BIOS set**, rsynced out of the library into RetroArch's `system/` rather than pointed at in place: cores
  treat that directory as writable scratch (Dolphin's `Sys` tree, PPSSPP's state), so it must be local.
- **The playlists**, regenerated from the library rather than scanned in-app, so the ROM-directory-to-core
  association lives in `games_retroarch_systems`. Adding a ROM means re-running the `retroarch` tag.
- **The per-core overrides and core options**, under `config/<library_name>/`, where `library_name` is what the
  built core reports at runtime, a third name for the same core (the GameCube core is `dolphin` on the buildbot,
  `Dolphin` in its `.info`, and reports `dolphin-emu`). It is a property of the build, so the role asks the cores
  rather than writing it down.
- **The shared thumbnail cache** in the library, the one thing RetroArch writes that hosts can share. Only the host
  whose mount is writable downloads into it; the rest read it. The library owns the directory the way it owns the
  BIOS set: the play asserts it exists and never creates it.
- **A udev rule** granting the desktop session read access to the mouse and keyboard, which `input_driver = udev`
  needs and the distro's `70-uaccess.rules` gives only to joysticks. Without it the gamepad works while the menu
  pointer and lightgun are dead.

Everything else RetroArch writes stays under `~/.var/app/org.libretro.RetroArch/config/retroarch`. Keeping every
writable path (saves, states, `system/`, cache) there is what lets a host mount the library read-only, so nothing
else may move into the library.

**Swapping a core orphans that system's saves.** RetroArch sorts saves and states into per-core directories keyed
by `library_name`. Save states cannot migrate; battery saves migrate only within an emulator family (Mednafen's
`.srm` moves between its cores; DeSmuME's `.dsv` is not a melonDS `.sav`). Move battery saves by hand and delete
the states.

Four helper scripts under [files/](./files/) do the core probing, playlist generation, thumbnail fetching, and
arcade name map regeneration. The role runs them, but each is standalone and can be run by hand to debug a single
stage: [files/README.md](./files/README.md).

## Handheld sync (Retroid Pocket Flip 2)

[files/retroid/](./files/retroid/) mirrors this same managed config onto a Retroid Pocket Flip 2 (Snapdragon 865,
stock Android + ES-DE), which Ansible cannot reach. `syncretroid` reads this role's `vars/main.yml` as the source
of truth, applies the Android divergences in `files/retroid/profile.yml`, and reconciles the result onto the device
over `adb` with the role's own ownership semantics. It reuses `retroarch-generate-playlists.py` unchanged.

The `retroid` tag renders it to `/usr/local/bin/syncretroid` with the ROM library mount and adb serial baked in, so
the command takes no arguments. The handheld is a USB peripheral of the controller rather than an inventory host,
so the command is installed on the controller (`delegate_to: localhost`) and gated on `games_install_retroid_sync`.
No playbook runs the sync itself; run it by hand. See [files/retroid/README.md](./files/retroid/README.md).
