# ansible-role-games

Installs gaming apt packages and flatpaks on Ubuntu, and configures RetroArch against the ROM library.

## Usage

```bash
make games
make games -- --tags flatpak
make games -- --tags retroarch
```

## Tags

| Tag       | Description                                                                                                                                                                                                                |
| --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| apt       | Native gaming packages                                                                                                                                                                                                     |
| bedrock   | Minecraft Bedrock launcher (BedrockOnLinux) from its release flatpak bundle, the `ntsync` module Wine 11 needs for fast synchronization, and a desktop entry that launches the game directly, carrying the game's own icon |
| flatpak   | Flatpak runtime, flathub remote, applications, extensions, and overrides                                                                                                                                                   |
| gamemode  | `/etc/gamemode.ini`, which is the screensaver inhibitor and nothing else                                                                                                                                                   |
| heroic    | Heroic install path and the store token-refresh timer                                                                                                                                                                      |
| lutris    | Lutris default install path, the prefix-teardown launcher, and a World of Warcraft entry plus desktop entry that launches it through Lutris without the client's window, where the Battle.net prefix holds the game        |
| retroarch | Libretro cores, BIOS, settings, per-core overrides, playlists, and thumbnails                                                                                                                                              |
| retroid   | `syncretroid`, the handheld sync command, installed on the controller                                                                                                                                                      |

## Variables

Host-settable knobs are in [defaults/main.yml](./defaults/main.yml), which comments each one. Everything else is
in [vars/main.yml](./vars/main.yml):

| Rule                                                                                      | Detail                                                                                                                                                                                                                                                                                             |
| ----------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Nothing in `vars/` is host-settable                                                       | Role vars outrank `host_vars`. It holds the canonical RetroArch data (`games_retroarch_systems`, `..._required_settings`, `..._core_overrides`, `..._core_options`, `..._controllers`), the derived paths, the upstream pins, the flatpak sandbox grants, and the fact-derived values              |
| Override the default a value derives from, not the derived value                          | `syncretroid` reads `vars/main.yml` directly and resolves no inventory, so a `host_vars` override reaches the desktops and silently not the handheld                                                                                                                                               |
| A `host_vars` override of a dict must restate the whole value                             | Ansible replaces dicts rather than merging them. `games_retroarch_extra_settings` avoids that for the one dict a host has reason to add to                                                                                                                                                         |
| `games_flatpak_common` is every host's set, the `games_install_*` flags the optional ones | `games_flatpak_apps` in `vars/` is the two together, which the tasks install, extend and override. A flag is two-way: off uninstalls the application, its permission override, its `~/.var/app` data and any runtime left unused. `host_vars` names the decision and the application ID stays here |

### Per-host settings

Site data or hardware the role cannot see. Each is asserted by the play, a guessed value failing silently.

| Setting                                             | Why                                                                                                                                                                                                        |
| --------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `games_retroarch_library_dir`                       | Where the host mounts the ROM library. The tag also asserts the library is mounted: an unmounted share looks exactly like an empty one                                                                     |
| `games_retroarch_controller`                        | Names a key of `games_retroarch_controllers`. RetroArch's `input_*_btn` and `input_*_axis` are _physical_ device indices, not RetroPad IDs, so a wrong value binds a different button rather than no-oping |
| `games_retroarch_video_refresh_rate`                | RetroArch derives the audio resampling ratio from it, so its 60.0 default mistimes every core on a high-refresh panel, heard as drift. "Estimate Screen Refresh Rate" in the menu reports it               |
| `games_retroid_library_dir`, `games_retroid_serial` | Baked into `syncretroid`. Asserted only when `games_install_retroid_sync` is on                                                                                                                            |

Read a new pad's indices out of its autoconfig profile and add an entry to `games_retroarch_controllers`:

```bash
flatpak run --command=grep org.libretro.RetroArch -E '^input_(r_y_minus_axis|r_y_plus_axis|l3_btn|r3_btn)' \
  "/app/share/libretro/autoconfig/udev/Microsoft_X-Box_Series_XS_pad.cfg"
```

### VRR

`vrr_runloop_enable` is an optional per-host setting, turned on in `games_retroarch_extra_settings` for a VRR
panel. The play asserts its preconditions:

| Precondition                              | Detail                                                                                                                                                |
| ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| No conflicting video-to-audio sync method | vsync must be on with a swap interval of 1 (or 0 for auto), and black frame insertion off. On a fixed-refresh panel leave VRR off and use BFI instead |
| VRR enabled outside RetroArch             | A compositor setting under Wayland; `Option "VariableRefresh"` in `xorg.conf.d` under X11, where it conflicts with `TearFree`                         |

## GameMode

`gamemoderun` raises the CPU governor and process priority for the game it wraps, and by default also holds an
`org.freedesktop.ScreenSaver` inhibitor for as long as that game runs. `games_gamemode_inhibit_screensaver` is
false, which turns that off: GNOME honours such an inhibitor for blanking and idle suspend alike, with no cap on
how long it may be held, so a play session otherwise keeps a static image lit for its whole length. A tiling
session is unaffected either way, providing no `org.freedesktop.ScreenSaver` for GameMode to reach.

| Constraint                                                                                  | Detail                                                                                                                                                                                                   |
| ------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| The launching account's `~/.config/gamemode.ini` is read after `/etc/gamemode.ini` and wins | A value set there overrides this role. `gamemoded` logs the files it loads at startup                                                                                                                    |
| Turning this off does not by itself make the screen blank during play                       | The game takes an inhibitor of its own: SDL and GLFW both do for any window they open. The floor under that is `desktop_idle_backstop_minutes` in the [desktop role](../desktop/README.md#idle-backstop) |

## RetroArch

**Close RetroArch before running the play.** It rewrites `retroarch.cfg` and its core options on exit
(`config_save_on_exit`), so a running instance overwrites whatever the play enforced. The `retroarch` tag asserts
it is not running.

What the role owns, and the constraint that shapes it:

| Owned                                                                                               | Constraint                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| --------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `retroarch.cfg`, key by key                                                                         | The file holds thousands of keys; the role owns only those in `games_retroarch_required_settings`. Settings changed in the app persist, and the managed keys snap back                                                                                                                                                                                                                                                                                                                                                                   |
| The cores directory                                                                                 | Libretro cores are not packaged for apt or flatpak, so they come from the same nightly buildbot the in-app Core Updater uses. There is nothing to pin, and every run refetches, which also repairs a core the flatpak runtime can no longer load after a runtime upgrade. A core no system runs is removed. Each is dlopened inside the sandbox to read its reported name, which doubles as the load check. The set is the desktop (x64) column of the [til notes](https://github.com/andornaut/til/blob/main/docs/retro-games.md#cores) |
| The BIOS set, rsynced out of the library into RetroArch's `system/` rather than pointed at in place | Cores treat that directory as writable scratch (Dolphin's `Sys` tree, PPSSPP's state)                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| The playlists, regenerated from the library rather than scanned in-app                              | The ROM-directory-to-core association lives in `games_retroarch_systems`, so adding a ROM means re-running the `retroarch` tag                                                                                                                                                                                                                                                                                                                                                                                                           |
| The per-core overrides and core options, under `config/<library_name>/`                             | `library_name` is what the built core reports at runtime, a third name for the same core (the GameCube core is `dolphin` on the buildbot, `Dolphin` in its `.info`, and reports `dolphin-emu`). A property of the build, so the role asks the cores rather than writing it down                                                                                                                                                                                                                                                          |
| The shared thumbnail cache in the library                                                           | The one thing RetroArch writes that hosts can share. Only the host whose mount is writable downloads into it. The play asserts the directory exists and never creates it                                                                                                                                                                                                                                                                                                                                                                 |
| A udev rule granting the desktop session read access to the mouse and keyboard                      | `input_driver = udev` needs it and the distro's `70-uaccess.rules` gives it only to joysticks. Without it the gamepad works while the menu pointer and lightgun are dead                                                                                                                                                                                                                                                                                                                                                                 |

Everything else RetroArch writes stays under `~/.var/app/org.libretro.RetroArch/config/retroarch`. Keeping every
writable path (saves, states, `system/`, cache) there is what lets a host mount the library read-only, so nothing
else may move into the library.

**Swapping a core orphans that system's saves.** RetroArch sorts saves and states into per-core directories keyed
by `library_name`. Save states cannot migrate; battery saves migrate only within an emulator family (Mednafen's
`.srm` moves between its cores; DeSmuME's `.dsv` is not a melonDS `.sav`). Move battery saves by hand and delete
the states.

The role has no dependencies: it installs `flatpak` and adds the flathub remote for `games_user` itself. Four
helper scripts under [files/](./files/) do the core probing, playlist generation, thumbnail fetching, and arcade
name map regeneration, each runnable by hand to debug a single stage: [files/README.md](./files/README.md).

### Convergence details

Behind the table above, the parts that are easy to undo by accident:

- **Canonical data is `roles/games/vars/main.yml`, not `defaults/`**: role vars outrank `host_vars`, and
  `syncretroid` reads that file directly, so a `host_vars` override would reach the desktops and silently not the
  handheld. Ansible replaces dicts rather than merging, so only `games_retroarch_extra_settings` is combined key by
  key; every other dict is not host-settable.
- **Cores use `get_url` then `unarchive` only when the archive changed.** The buildbot never answers `304`, so
  archives are fetched every run either way, but this way a run reports a core changed only when a binary moved.
  Letting `unarchive` download re-extracts and reports everything changed every run.
- **The playlist generator owns its directory** and deletes a `.lpl` whose system left `games_retroarch_systems`,
  but only files it wrote (favourites and history live in `builtin/`), and never replaces a playlist with an empty
  one. A `.zip` is listed by its own path, not `archive.zip#rom.sfc`, so it never opens every archive over the
  network mount. Multi-disc layout follows whether the core reads an `.m3u`: those that do get a dot-prefixed
  directory plus an `.m3u` beside it and automatic disc-swap; 3DO and GameCube do not, so the entry points at disc 1.
- **Overrides are written whole, core options key by key**: an override holds only what differs from the global
  config, whereas RetroArch writes every option a core exposes into the `.opt`, so writing that whole would discard
  every option the role has no opinion on.
- **Read capabilities off the build, not the docs.** Rewind and preemptive frames come from one `.info` field
  (`grep savestate_features <info_dir>/*_libretro.info`); core options are namespaced and undocumented, so read them
  out of the built core with `strings`. ParaLLEl is Vulkan-only and requests a Vulkan context only when its
  `rdp-plugin` option is `parallel`, so that option and the `video_driver` override must be set together.
- **The input rule also drops the `ID_INPUT_MOUSE` tag of one idle KVM/virtual HID.** RetroArch picks
  `input_player1_mouse_index` by enumeration order, not name, so a virtual HID that emits nothing takes slot 0 and
  every click lands on the dead device while the cursor still moves. Setting the index by hand does not fix it, the
  order being unstable across launches.
- **The thumbnail directory must be setgid and in the library's group**, or the share will not serve what RetroArch
  creates under it. The play cannot police this: a network client is served ownership and mode the protocol invents.

## Lutris

Where Battle.net's prefix holds World of Warcraft (`_retail_/Wow.exe`), the `lutris` tag registers the game as its
own Lutris entry and installs a desktop entry that launches `lutris:rungame/world-of-warcraft` through
[`files/lutris-launch-game.py`](files/lutris-launch-game.py): Lutris launches the game without showing its window,
and the client shows the new entry after its next start.

| Detail                                                                     | Why                                                                                                                                                                                                                                         |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| The entry is Battle.net's executable with `--exec="launch WoW"`            | The client launches the game under its own session, so no password or authenticator prompt. `Wow.exe` run directly asks for both on every launch. Set Battle.net's "When I launch a game" to exit, or its window stays behind the game      |
| Its configuration is derived from Battle.net's on every run                | The `game`, `system` and `wine` sections are copied and only `args` differs, so a runner or environment change made to Battle.net in the client follows. A change made to the World of Warcraft entry itself is overwritten by the next run |
| The icon is the one lutris.net serves for the slug, under `~/.local/share` | Lutris keeps its own copy inside the sandbox, where the host's launcher does not look. Fetched once, and left alone once present                                                                                                            |
| Nothing is removed                                                         | Uninstalling the game leaves the entry, which then launches Battle.net on the game's page. Delete it in the client                                                                                                                          |

### Stale prefixes

Lutris leaves a Battle.net prefix running after it reports the game stopped, and the next launch then fails.
`lutris-launch-game.py` tears the prefix down before handing off, so every launch through the desktop entry starts
clean.

| Detail                                                                  | Why                                                                                                                                                                                                                                                                                      |
| ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Lutris cannot stop the prefix itself                                    | Its `ProcessWatcher` never signals a process named in `exclude_processes` (`Agent.exe`, `Battle.net Helper.exe`) nor in its own `SYSTEM_PROCESSES` (`wineserver` among them), and it misses processes systemd reparented                                                                 |
| A survivor breaks the next launch                                       | It holds the Steam runtime's `.ref` lock, so the launch cannot rebuild the merged `ld.so.cache`, falls back to its previous `LD_LIBRARY_PATH`, and Proton's python fails on `libffi.so.8`. The runtime ships only `libffi.so.8.1.4`, with no SONAME symlink, so nothing else resolves it |
| The teardown runs on the host, not in the sandbox                       | Each `flatpak run` is its own bubblewrap instance with its own PID namespace, so a Lutris prelaunch hook sees neither the previous launch's processes nor its own container's. The host sees every one of them                                                                           |
| Processes are matched on an exact `WINEPREFIX`/`STEAM_COMPAT_DATA_PATH` | Read from `/proc/<pid>/environ`, and compared whole rather than by path prefix, so a sibling prefix is not swept up. `SIGTERM`, then `SIGKILL` five seconds later                                                                                                                        |
| Launching from the Lutris client window bypasses it                     | Only the desktop entry runs the launcher. A prefix left running that way is cleared by the next launch from the desktop entry, or by a reboot                                                                                                                                            |
| The prefix is Battle.net's, shared with the client                      | An intentionally open Battle.net window is torn down with it. The entry launches Battle.net again anyway, `--exec="launch WoW"` going through the client                                                                                                                                 |

## Handheld sync (Retroid Pocket Flip 2)

[files/retroid/](./files/retroid/) mirrors this managed config onto a Retroid Pocket Flip 2 (stock Android +
ES-DE), which Ansible cannot reach. [files/retroid/README.md](./files/retroid/README.md) covers the device side:
the values that must be read off it by hand, the shader setup, and the failure modes.

- The `retroid` tag installs `/usr/local/bin/syncretroid`, a wrapper ([templates/syncretroid.j2](./templates/syncretroid.j2))
  that runs `files/retroid/syncretroid.py` from this checkout with the ROM library mount and adb serial baked in,
  so the command takes no arguments. An edit to the script or its data applies without re-running the role; re-run
  the tag if the checkout moves or either baked-in value changes.
- The handheld is a USB peripheral of the controller rather than an inventory host, so the command is installed on
  the controller (`delegate_to: localhost`) and gated on `games_install_retroid_sync`.
- No playbook runs the sync itself. Run it by hand: the runbook and the device's storage layout are in the
  [retroid-sync skill](../../.claude/skills/retroid-sync/SKILL.md).
