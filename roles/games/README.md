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
| bedrock | Minecraft Bedrock launcher (BedrockOnLinux) from its release flatpak bundle, and the `ntsync` module Wine 11 needs for fast synchronization |
| flatpak | Flatpak runtime, flathub remote, applications, extensions, and overrides |
| heroic | Heroic install path and the store token-refresh timer |
| lutris | Lutris default install path |
| retroarch | Libretro cores, BIOS, settings, per-core overrides, playlists, and thumbnails |
| retroid | `syncretroid`, the handheld sync command, installed on the controller |

## Variables

Host-settable knobs are in [defaults/main.yml](./defaults/main.yml), which comments each one. Everything else is
in [vars/main.yml](./vars/main.yml):

| Rule | Detail |
| --- | --- |
| Nothing in `vars/` is host-settable | Role vars outrank `host_vars`. It holds the canonical RetroArch data (`games_retroarch_systems`, `..._required_settings`, `..._core_overrides`, `..._core_options`, `..._controllers`), the derived paths, the upstream pins, the flatpak sandbox grants, and the fact-derived values |
| Override the default a value derives from, not the derived value | `syncretroid` reads `vars/main.yml` directly and resolves no inventory, so a `host_vars` override reaches the desktops and silently not the handheld |
| A `host_vars` override of a dict must restate the whole value | Ansible replaces dicts rather than merging them. `games_retroarch_extra_settings` exists to avoid that for the one dict a host has reason to add to |

### Per-host settings

These have no usable default and are asserted by the play. Each is site data or hardware the role cannot see,
where a guessed value would fail silently.

| Setting | Why |
| --- | --- |
| `games_retroarch_library_dir` | Where the host mounts the ROM library. Site data, so it is not in `defaults/` either: `host_vars/` must set it. The tag also asserts the library is mounted: an unmounted share looks exactly like an empty one |
| `games_retroarch_controller` | Names a key of `games_retroarch_controllers`. RetroArch's `input_*_btn` and `input_*_axis` are *physical* device indices, not RetroPad IDs, so a wrong value binds a different button rather than no-oping |
| `games_retroarch_video_refresh_rate` | RetroArch derives the audio resampling ratio from it, so its 60.0 default mistimes every core on a high-refresh panel, heard as drift. "Estimate Screen Refresh Rate" in the menu reports it |
| `games_retroid_library_dir`, `games_retroid_serial` | Baked into `syncretroid`. Asserted only when `games_install_retroid_sync` is on |

Read a new pad's indices out of its autoconfig profile and add an entry to `games_retroarch_controllers`:

```bash
flatpak run --command=grep org.libretro.RetroArch -E '^input_(r_y_minus_axis|r_y_plus_axis|l3_btn|r3_btn)' \
  "/app/share/libretro/autoconfig/udev/Microsoft_X-Box_Series_XS_pad.cfg"
```

### VRR

`vrr_runloop_enable` is the one optional per-host setting, turned on in `games_retroarch_extra_settings` for a VRR
panel. The play asserts its preconditions:

| Precondition | Detail |
| --- | --- |
| No other video-to-audio sync method | vsync, a swap interval above 1, and black frame insertion all conflict. On a fixed-refresh panel leave it off and use BFI instead |
| VRR enabled outside RetroArch | A compositor setting under Wayland; `Option "VariableRefresh"` in `xorg.conf.d` under X11, where it conflicts with `TearFree` |

## RetroArch

**Close RetroArch before running the play.** It rewrites `retroarch.cfg` and its core options on exit
(`config_save_on_exit`), so a running instance overwrites whatever the play enforced. The `retroarch` tag asserts
it is not running.

What the role owns, and the constraint that shapes it:

| Owned | Constraint |
| --- | --- |
| `retroarch.cfg`, key by key | The file holds thousands of keys; the role owns only those in `games_retroarch_required_settings`. Settings changed in the app persist, and the managed keys snap back |
| The cores directory | Libretro cores are not packaged for apt or flatpak, so they come from the same nightly buildbot the in-app Core Updater uses. Nightlies, so there is nothing to pin, and every run refetches, which also repairs a core the flatpak runtime can no longer load after a runtime upgrade. A core no system runs is removed so it cannot linger in "Load Core". Each is dlopened inside the sandbox to read its reported name, which doubles as the load check. The set is the desktop (x64) column of the [til notes](https://github.com/andornaut/til/blob/main/docs/retro-games.md#cores) |
| The BIOS set, rsynced out of the library into RetroArch's `system/` rather than pointed at in place | Cores treat that directory as writable scratch (Dolphin's `Sys` tree, PPSSPP's state), so it must be local |
| The playlists, regenerated from the library rather than scanned in-app | The ROM-directory-to-core association lives in `games_retroarch_systems`, so adding a ROM means re-running the `retroarch` tag |
| The per-core overrides and core options, under `config/<library_name>/` | `library_name` is what the built core reports at runtime, a third name for the same core (the GameCube core is `dolphin` on the buildbot, `Dolphin` in its `.info`, and reports `dolphin-emu`). It is a property of the build, so the role asks the cores rather than writing it down |
| The shared thumbnail cache in the library | The one thing RetroArch writes that hosts can share. Only the host whose mount is writable downloads into it; the rest read it. The library owns the directory as it owns the BIOS set: the play asserts it exists and never creates it |
| A udev rule granting the desktop session read access to the mouse and keyboard | `input_driver = udev` needs it and the distro's `70-uaccess.rules` gives it only to joysticks. Without it the gamepad works while the menu pointer and lightgun are dead |

Everything else RetroArch writes stays under `~/.var/app/org.libretro.RetroArch/config/retroarch`. Keeping every
writable path (saves, states, `system/`, cache) there is what lets a host mount the library read-only, so nothing
else may move into the library.

**Swapping a core orphans that system's saves.** RetroArch sorts saves and states into per-core directories keyed
by `library_name`. Save states cannot migrate; battery saves migrate only within an emulator family (Mednafen's
`.srm` moves between its cores; DeSmuME's `.dsv` is not a melonDS `.sav`). Move battery saves by hand and delete
the states.

The role has no dependencies: it installs `flatpak` and adds the flathub remote for `games_user` itself, so it
runs standalone on a host that has never had the [desktop](../desktop/) role applied.

Four helper scripts under [files/](./files/) do the core probing, playlist generation, thumbnail fetching, and
arcade name map regeneration. The role runs them, but each is standalone and can be run by hand to debug a single
stage: [files/README.md](./files/README.md).

## Handheld sync (Retroid Pocket Flip 2)

[files/retroid/](./files/retroid/) mirrors this managed config onto a Retroid Pocket Flip 2 (stock Android +
ES-DE), which Ansible cannot reach. `syncretroid` reads this role's [vars/main.yml](./vars/main.yml) as the source
of truth, applies the Android divergences in `files/retroid/profile.yml`, and reconciles the result onto the device
over `adb`. See [files/retroid/README.md](./files/retroid/README.md).

- The `retroid` tag installs `/usr/local/bin/syncretroid`, a wrapper that runs `files/retroid/syncretroid.py` from
  this checkout with the ROM library mount and adb serial baked in, so the command takes no arguments. An edit to
  the script or to the data it reads applies without re-running the role; re-run the tag if the checkout moves.
- The handheld is a USB peripheral of the controller rather than an inventory host, so the command is installed on
  the controller (`delegate_to: localhost`) and gated on `games_install_retroid_sync`.
- No playbook runs the sync itself. Run it by hand.
