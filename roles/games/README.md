# ansible-role-games

Installs gaming apt packages and flatpaks on Ubuntu, and configures RetroArch for the ROM library.

## Usage

```bash
make games
make games -- --tags flatpak
make games -- --tags retroarch
```

## Tags

| Tag         | Description                                                                                                                                                                                                                          |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| app-entries | Desktop entry overrides in `~/.local/share/applications` from `games_app_entry_overrides`, which hide an entry or set its categories; a copy no longer named is pruned. Same mechanism as the [desktop](../desktop/README.md) role's |
| apt         | Native gaming packages                                                                                                                                                                                                               |
| bedrock     | Minecraft Bedrock launcher and its desktop entry: [Minecraft (Bedrock)](#minecraft-bedrock)                                                                                                                                          |
| flatpak     | Flatpak runtime, flathub remote, applications, extensions and overrides                                                                                                                                                              |
| gamemode    | `/etc/gamemode.ini` and `gamemode` group membership: [GameMode](#gamemode)                                                                                                                                                           |
| gamescope   | gamescope on the host: the archive package on Ubuntu >= 26.04, built from a pinned tag into `/usr/local` below that. The launchers' wrapper belongs to the bedrock and lutris tags                                                   |
| heroic      | Heroic install path and the store token-refresh timer                                                                                                                                                                                |
| lutris      | Lutris default install path, gamescope settings, the sandbox PATH grant for the gamescope wrapper, the prefix-teardown launcher and the World of Warcraft entry: [Lutris](#lutris)                                                   |
| retroarch   | Libretro cores, BIOS, settings, per-core overrides, playlists and thumbnails                                                                                                                                                         |
| retroid     | `syncretroid`, the handheld sync command, installed on the controller                                                                                                                                                                |

## Variables

Host-settable values are in [defaults/main.yml](./defaults/main.yml), each commented. The rest are in
[vars/main.yml](./vars/main.yml), which is not host-settable (see [Notes](#notes)).

These describe site data or hardware the role cannot detect. The play asserts each one, because a wrong value
produces no error:

| Variable                                            | Purpose                                                                                                                                                                                                                                            |
| --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `games_retroarch_library_dir`                       | Where the host mounts the ROM library. The tag also asserts the library is mounted: an unmounted share looks the same as an empty one                                                                                                              |
| `games_retroarch_controller`                        | A key of `games_retroarch_controllers`. RetroArch's `input_*_btn` and `input_*_axis` are physical device indices, not RetroPad IDs, so a wrong value binds a different button instead of none. [Operations](#operations) reads a new pad's indices |
| `games_retroarch_video_refresh_rate`                | RetroArch derives the audio resampling ratio from it. The 60.0 default mistimes every core on a high-refresh panel, heard as audio drift. The menu's "Estimate Screen Refresh Rate" reports the value                                              |
| `games_gamescope_resolution`                        | The panel's mode as WIDTHxHEIGHT, used as gamescope's output size. Asserted when `games_gamescope_enabled` is on. `xrandr --current` names it                                                                                                      |
| `games_retroid_library_dir`, `games_retroid_serial` | Rendered into `syncretroid`. Asserted only when `games_install_retroid_sync` is on                                                                                                                                                                 |

## Installed files

| Path                                                            | Purpose                                                                                          |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `/etc/gamemode.ini`                                             | GameMode settings                                                                                |
| `/etc/udev/rules.d/70-ansible-role-games-retroarch-input.rules` | Mouse and keyboard read access for RetroArch                                                     |
| `/usr/local/bin/lutris-launch-game`                             | Prefix-teardown launcher, [files/lutris-launch-game.py](files/lutris-launch-game.py)             |
| `/usr/local/bin/syncretroid`                                    | Handheld sync wrapper, on the controller                                                         |
| `~/.local/bin/world-of-warcraft-launch.sh`                      | Runs the launcher for the World of Warcraft prefix                                               |
| `~/.local/bin/minecraft-bedrock-launch.sh`                      | Launches Minecraft (Bedrock), or focuses its window if already running                           |
| `~/.local/bin/heroic-refresh-tokens`                            | Refreshes Heroic's store tokens, run by `heroic-token-refresh.timer` in `~/.config/systemd/user` |
| `~/.local/share/gamescope-helpers`                              | `games_gamescope_helper_dir`: the gamescope wrapper                                              |
| `~/.local/share/bol-helpers`                                    | `games_bedrock_helper_dir`: a vendored xrandr for BedrockOnLinux                                 |
| `~/.local/state/lutris-launch-game/<slug>.log`                  | Launcher log                                                                                     |

## Gamescope

A game that sizes its window to the display without setting `_NET_WM_STATE_FULLSCREEN` has GNOME's top bar and
dock drawn over it, and mutter can composite such a window as a blank surface after the game recreates it across
a display-mode change. `games_gamescope_enabled` runs Lutris games and Minecraft (Bedrock) inside gamescope, which
sets the fullscreen state itself and gives the game its own nested compositor, at a cost of about one frame of
latency. It is off by default; a host enables it together with `games_gamescope_resolution`. It works on X11 and
Wayland, gamescope selecting its own backend. With the flag off, Lutris's own gamescope settings are not changed.

On Ubuntu >= 26.04 the host gamescope comes from the archive. Below that, `gamescope.yml` builds
`games_gamescope_version` into `/usr/local`. When the archive's Wayland is below 1.23, the minimum for that tag's
wlroots, it first builds Wayland `games_gamescope_wayland_version` into `games_gamescope_deps_prefix`, which only
the gamescope build finds, through `PKG_CONFIG_PATH` and an rpath. The build and its dependency install are
skipped while `/usr/local/bin/gamescope --version` reports the tag.

### Sandbox wrapper

Lutris games get gamescope through `gamescope: true` in `system.yml`, and Minecraft (Bedrock) through
`BOL_GAMESCOPE` in its flatpak override. Each launcher runs the first `gamescope` on its sandbox PATH, which is the
role's wrapper, granted to both sandboxes from `games_gamescope_helper_dir`. Plain gamescope cannot present either
launcher's game:

- **Symptom:** on an X11 host the Gamescope WSI layer fails its swapchain with `Failed to get Xwayland server id`.
  On a Wayland host the game stops on a `Hooking has failed somewhere!` dialog.
- **Cause:** both launchers run the game under umu, in a pressure-vessel sub-sandbox that the flatpak portal
  spawns. The portal sets that sub-sandbox's `DISPLAY` and `WAYLAND_DISPLAY` to the host's after applying every
  environment option, so the game connects to the host X server and gamescope's nested server goes unused. On
  Wayland, the WSI layer sees a `WAYLAND_DISPLAY` that is not gamescope's socket and concludes it is not under
  gamescope. Nothing in umu, pressure-vessel or Proton passes either variable past that point.
- **Fix:** the wrapper sets both variables again inside the container:

| File in `games_gamescope_helper_dir`      | Purpose                                                                                                                                                                                                                                                                   |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `gamescope`                               | Runs the extension's binary with the game command prefixed by `gamescope-child`. Called with no command, which is how Lutris reads `--help` for a version's options, it runs the binary unchanged                                                                         |
| `gamescope-child`                         | Runs as gamescope's child, where `DISPLAY` is the nested server. Exports it as `GAMESCOPE_CHILD_XDISPLAY`, adds the library to `LD_PRELOAD`, and unsets `XDG_CURRENT_DESKTOP` and `XDG_SESSION_DESKTOP`, because umu-run drops `LD_PRELOAD` when either reads `gamescope` |
| `lib/<multiarch>/libgamescope-display.so` | Preloaded into every process of the game container: pressure-vessel forwards `LD_PRELOAD` as `--ld-preload`. Its constructor sets `DISPLAY` from `GAMESCOPE_CHILD_XDISPLAY` and unsets `WAYLAND_DISPLAY`, as gamescope does for its child                                 |

| Constraint                     | Detail                                                                                                                                                                                                                                                                                                                                         |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Two preload builds             | `x86_64-linux-gnu` and `i386-linux-gnu`, both named by one `LD_PRELOAD` entry through ld.so's `$LIB`, because a prefix runs both. `gamescope-wrapper.yml` builds them on the host and installs `gcc` and its multilib                                                                                                                          |
| Sandbox binary                 | The sandboxes use gamescope from the `org.freedesktop.Platform.VulkanLayer.gamescope` extension, not the host's. The wrapper runs it by path: the extension's `bin` is behind the wrapper on Lutris's PATH and absent from BedrockOnLinux's. Neither launcher uses the host gamescope                                                          |
| Extension branch               | `flatpak_vulkan.yml` installs the extension, binary and WSI layer together, on each branch an installed launcher's runtime mounts. It reads the branch from the runtime's extension point after every launcher install, because an update can change it                                                                                        |
| Keyboard map                   | The nested server takes its keymap only from the `XKB_DEFAULT_*` variables, so the session's Caps Lock remap does not apply in gamescope's window. Both launchers' overrides set `XKB_DEFAULT_OPTIONS` from `games_gamescope_xkb_options`. A running game keeps the map it started with                                                        |
| 1280x720 default               | gamescope's nested output defaults to 1280x720. Lutris passes no size when `gamescope_output_res` and `gamescope_game_res` are unset, and BedrockOnLinux sizes from its own xrandr probe when `BOL_GAMESCOPE` is `1`, so the role gives both `games_gamescope_resolution`. Symptom: the game runs but is not visible                           |
| Resolution is not probed       | A probe needs `games_user` logged in during the run, and a run with no session would write `gamescope: true` without a size, giving the 1280x720 window. The assert in `main.yml` requires the flag and the size together                                                                                                                      |
| BedrockOnLinux's own setting   | Its "Gamescope arguments" setting outranks `BOL_GAMESCOPE`: the launcher reads it first and the variable only when it is empty. `0`, `off` or `false` there disables gamescope while the role reports the override as converged. The setting is in the launcher's data directory, which the role does not read. Clear it in the launcher's GUI |
| `/proc` shows the host display | `/proc/<pid>/environ` still shows the host's `DISPLAY` and `WAYLAND_DISPLAY` for the game, because `setenv` does not rewrite that block. Check for the WSI layer's `Created swapchain` line, or for the window on gamescope's display ([Operations](#operations))                                                                              |
| Screenshots                    | `import -window root` captures a fullscreen Vulkan window as black. Use gamescope's own screenshot ([Operations](#operations)). The running gamescope writes the file, so the path must be inside a grant it already has, such as its `~/.var/app/<app-id>/data`                                                                               |
| `gamescope-brokey`             | In the flatpak, `bin/gamescope` is a shell wrapper that runs `gamescope-brokey`, so log lines read `[gamescope-brokey]`. The name says nothing about the binary's health                                                                                                                                                                       |
| `Starting headless backend`    | wlroots logs it for gamescope's nested wlserver on every run, Wayland included. It is not the output backend. Look for the window with `xwininfo -root -children`                                                                                                                                                                              |

## GameMode

`gamemoderun` raises the CPU governor and process priority for the game it wraps, and by default holds an
`org.freedesktop.ScreenSaver` inhibitor while the game runs. `games_gamemode_inhibit_screensaver` is false, which
disables that inhibitor: GNOME honours it for blanking and idle suspend with no time limit, so a play session
would otherwise keep a static image lit for its whole length. Tiling sessions provide no
`org.freedesktop.ScreenSaver`, so the setting has no effect there.

| Constraint                        | Detail                                                                                                                                                                                                                                                                                                                                                                                  |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| User file wins                    | The launching account's `~/.config/gamemode.ini` is read after `/etc/gamemode.ini` and overrides it. `gamemoded` logs the files it loads at startup                                                                                                                                                                                                                                     |
| Helpers need the `gamemode` group | `cpugovctl`, `cpucorectl`, `gpuclockctl` and `procsysctl` run as root through `pkexec`. The package's polkit rule grants them to the `gamemode` group and adds nobody to it, so with the package defaults the daemon enters Game Mode but applies no governor, pinning or split-lock change, logging each refusal as `Not authorized`. The tag adds `games_gamemode_users` to the group |
| The grant is account-wide         | Any process of a group member can run the four helpers without a prompt, and a change made by a process that bypasses the daemon is never reverted                                                                                                                                                                                                                                      |
| Host-wide effect                  | Upstream's `gamemode.ini` defaults apply: `desiredgov=performance` and `disable_splitlock=1` reach every core and `/proc/sys/kernel/split_lock_mitigate` while any client is registered, and are restored when the last one leaves                                                                                                                                                      |
| Restore values are in memory      | The daemon keeps the values it restores in memory only. If it dies mid-session, its replacement takes the game-time values as its baseline and never restores the originals                                                                                                                                                                                                             |
| Lutris games do not register      | Lutris's GameMode option prefixes the launch with `gamemoderun`, whose client library cannot find `libgamemode.so` in umu's pressure-vessel container, one log line per process start. `gamemoderun` itself registers from outside the container, so the host-wide settings apply; the per-process settings (ioprio, pinning) skip the game's PIDs                                      |
| The screen still does not blank   | The game takes its own inhibitor: SDL and GLFW both take one for any window they open. The limit above that is `desktop_idle_backstop_minutes` in the [desktop role](../desktop/README.md#idle-backstop)                                                                                                                                                                                |

## RetroArch

**Close RetroArch before running the play.** It rewrites `retroarch.cfg` and its core options on exit
(`config_save_on_exit`), which overwrites what the play set. The `retroarch` tag asserts it is not running.

| Owned                                     | Detail                                                                                                                                                                                                                                                              |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `retroarch.cfg`, per key                  | The role owns only the keys in `games_retroarch_required_settings`. Other settings changed in the app persist; managed keys are reset by the next run                                                                                                               |
| The cores directory                       | Libretro cores have no apt or flatpak package, so they come from the nightly buildbot the in-app Core Updater uses. The set is the desktop (x64) column of the [til notes](https://github.com/andornaut/til/blob/main/docs/retro-games.md#cores)                    |
| The BIOS set                              | Copied with rsync from the library into RetroArch's `system/`, not referenced in place: cores write scratch data there (Dolphin's `Sys` tree, PPSSPP's state)                                                                                                       |
| The playlists                             | Generated from the library, not scanned in the app. `games_retroarch_systems` maps ROM directories to cores, so a new ROM needs a rerun of the `retroarch` tag                                                                                                      |
| Per-core overrides and core options       | Under `config/<library_name>/`. `library_name` is the name the built core reports at runtime, a third name for the same core: the GameCube core is `dolphin` on the buildbot, `Dolphin` in its `.info`, and reports `dolphin-emu`. The role reads it from the cores |
| The shared thumbnail cache in the library | The only RetroArch output hosts can share. Only a host whose mount is writable downloads into it. The play asserts the directory exists and does not create it                                                                                                      |
| A udev input rule                         | Gives the desktop session read access to mice and keyboards. `input_driver = udev` needs it, and the distro's `70-uaccess.rules` grants it only for joysticks. Without it the gamepad works but the menu pointer and lightgun do not                                |

| Constraint                                | Detail                                                                                                                                                                                                                                                                                                                                                        |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Writable paths stay in the sandbox        | Everything else RetroArch writes stays under `~/.var/app/org.libretro.RetroArch/config/retroarch`. Keeping every writable path (saves, states, `system/`, cache) there lets a host mount the library read-only, so nothing else may move into the library                                                                                                     |
| Swapping a core orphans its saves         | Saves and states are stored per core, keyed by `library_name`. States cannot migrate. Battery saves migrate only within an emulator family: Mednafen's `.srm` moves between its cores, and DeSmuME's `.dsv` is not a melonDS `.sav`. Move battery saves by hand and delete the states                                                                         |
| Cores are refetched every run             | There is nothing to pin. Refetching also repairs a core the flatpak runtime can no longer load after a runtime upgrade. A core no system uses is removed. Each core is loaded with dlopen in the sandbox to read its reported name, which is also the load check                                                                                              |
| Core downloads                            | `get_url`, then `unarchive` only when the archive changed. The buildbot never returns `304`, so every run downloads the archives, but a core reports changed only when its binary changed. Letting `unarchive` download re-extracts and reports every core changed on every run                                                                               |
| The playlist generator owns its directory | It deletes a `.lpl` whose system left `games_retroarch_systems`, but only files it wrote (favourites and history are in `builtin/`), and never replaces a playlist with an empty one                                                                                                                                                                          |
| Zip entries                               | A `.zip` is listed by its own path, not `archive.zip#rom.sfc`, so RetroArch does not open every archive over the network mount                                                                                                                                                                                                                                |
| Multi-disc games                          | Cores that read `.m3u` get a dot-prefixed directory, an `.m3u` beside it, and automatic disc swap. 3DO and GameCube cores do not, so their entry points at disc 1                                                                                                                                                                                             |
| Overrides whole, core options per key     | An override holds only what differs from the global config. RetroArch writes every option a core exposes into its `.opt`, so writing that file whole would discard every option the role does not set                                                                                                                                                         |
| Read capabilities from the build          | Rewind and preemptive frames come from one `.info` field ([Operations](#operations)). Core options are namespaced and undocumented, so read them from the built core with `strings`                                                                                                                                                                           |
| ParaLLEl                                  | Vulkan-only, and it requests a Vulkan context only when its `rdp-plugin` option is `parallel`. Set that option and the `video_driver` override together                                                                                                                                                                                                       |
| Idle virtual HID                          | The input rule also removes the `ID_INPUT_MOUSE` tag from one idle KVM virtual HID. RetroArch picks `input_player1_mouse_index` by enumeration order, not name, so a virtual HID that emits nothing takes slot 0 and every click goes to it while the cursor still moves. Setting the index by hand does not work, because the order changes between launches |
| Thumbnail directory permissions           | Must be setgid and in the library's group, or the share does not serve what RetroArch creates in it. The play cannot check this: a network client sees an ownership and mode that the protocol invents                                                                                                                                                        |
| VRR sync method                           | `vrr_runloop_enable` is set per host in `games_retroarch_extra_settings` for a VRR panel. The play asserts vsync is on with a swap interval of 1 (or 0 for auto) and black frame insertion is off. On a fixed-refresh panel leave VRR off and use BFI                                                                                                         |
| VRR outside RetroArch                     | The play asserts VRR is enabled for the display: a compositor setting under Wayland, or `Option "VariableRefresh"` in `xorg.conf.d` under X11, where it conflicts with `TearFree`                                                                                                                                                                             |
| Helper scripts                            | Four scripts under [files/](./files/) probe cores, generate playlists, fetch thumbnails and regenerate the arcade name map. Each runs by hand to debug one stage: [files/README.md](./files/README.md)                                                                                                                                                        |

## Minecraft (Bedrock)

| Constraint    | Detail                                                                                                                                  |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Install       | BedrockOnLinux from its release flatpak bundle                                                                                          |
| `ntsync`      | Loaded now and at every boot when the kernel ships it: Wine 11 has no esync or fsync, so `ntsync` is its only fast synchronization path |
| Desktop entry | Launches the game directly, with the game's own icon                                                                                    |
| Sandbox PATH  | Grants `games_bedrock_helper_dir`, which holds a vendored xrandr, and the gamescope wrapper                                             |

## Lutris

Where Battle.net's prefix contains World of Warcraft (`_retail_/Wow.exe`), the `lutris` tag registers the game as
its own Lutris entry and installs a desktop entry that launches `lutris:rungame/world-of-warcraft` through
[files/lutris-launch-game.py](files/lutris-launch-game.py). Lutris starts the game without showing its window. The
client lists the new entry after its next start.

| Constraint                           | Detail                                                                                                                                                                                                                                                                                                                                                                              |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Launched through Battle.net          | The entry is Battle.net's executable with `--exec="launch WoW"`. The client launches the game in its own session, so there is no password or authenticator prompt; `Wow.exe` run directly asks for both on every launch                                                                                                                                                             |
| Configuration copied from Battle.net | The `game`, `system` and `wine` sections are copied on every run and only `args` differs, so runner and environment changes made to Battle.net in the client carry over. A change made to the World of Warcraft entry is overwritten by the next run                                                                                                                                |
| Prefix location                      | Read from Battle.net's own Lutris configuration. `pga.db` names the configuration file, which is not always the slug, so the probe and the teardown use the prefix the client uses, not one derived from the default install path. An unregistered Battle.net, or a prefix without `_retail_/Wow.exe`, produces a warning and nothing is registered                                 |
| Icon                                 | The one lutris.net serves for the slug, stored under `~/.local/share`: Lutris keeps its copy inside the sandbox, where the host's launcher does not look. Downloaded once, kept once present, and not fatal on failure: it is the tag's only network access, and the desktop entry is installed before it                                                                           |
| Nothing is removed                   | Uninstalling the game leaves the entry, which then opens Battle.net on the game's page. Delete it in the client                                                                                                                                                                                                                                                                     |
| `Exec` has no argument               | The entry runs `~/.local/bin/world-of-warcraft-launch.sh`, rendered with the prefix shell-quoted, and the launcher reads the game's name from Lutris's `pga.db`. nwg-drawer joins a quoted argument's words and passes them to `env -S`, which splits them again, so the launcher would exit on its usage line with nothing on screen. rofi and GNOME follow the desktop entry spec |
| Stale prefix teardown                | Lutris leaves a Battle.net prefix running after it reports the game stopped, and the next launch then fails. The launcher stops that session before handing off to Lutris. Its module docstring describes how                                                                                                                                                                       |
| Shared with Battle.net               | The prefix is Battle.net's, so the teardown also closes a Battle.net window that was left open. The entry starts Battle.net again, because `--exec="launch WoW"` goes through the client                                                                                                                                                                                            |
| Launching from the Lutris window     | Bypasses the teardown: only the desktop entry runs the launcher. A prefix left running after such a launch is cleared by the next launch from the desktop entry, or by a reboot                                                                                                                                                                                                     |
| Second click                         | During a launch, a second click is reported as already running at once if the first session has a window on screen. Otherwise it waits up to thirty seconds, its banner saying so, then reports that the game did not start. After the launch, a click on a session with a window leaves it alone, and a click on one without a window tears it down and launches again             |
| Slow first launch                    | The first launch after a GE-Proton release downloads and unpacks it before anything appears; the banner says a Proton update is being installed                                                                                                                                                                                                                                     |
| Failure banner                       | A failed launch shows a twenty-second banner and leaves nothing in the message list                                                                                                                                                                                                                                                                                                 |
| Log                                  | `~/.local/state/lutris-launch-game/<slug>.log`, under `XDG_STATE_HOME` when set, rotated at 1 MiB. A desktop entry's stderr is discarded, so read the log first when a launch does nothing                                                                                                                                                                                          |

## Handheld sync (Retroid Pocket Flip 2)

[files/retroid/](./files/retroid/) copies this role's RetroArch configuration to a Retroid Pocket Flip 2 (stock
Android and ES-DE), which Ansible cannot reach. [files/retroid/README.md](./files/retroid/README.md) covers the
device side: the values read from the device by hand, the shader setup, and the failure modes.

| Constraint                  | Detail                                                                                                                                                                                                                                                         |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Wrapper                     | The `retroid` tag installs `/usr/local/bin/syncretroid` ([templates/syncretroid.j2](./templates/syncretroid.j2)), which runs `files/retroid/syncretroid.py` from this checkout with the ROM library mount and adb serial rendered in, so it takes no arguments |
| When to rerun the tag       | An edit to the script or its data applies without rerunning the role. Rerun the tag when the checkout moves or either rendered value changes                                                                                                                   |
| Installed on the controller | The handheld is a USB device of the controller, not an inventory host, so the command is installed there (`delegate_to: localhost`), gated on `games_install_retroid_sync`                                                                                     |
| The sync is manual          | No playbook runs it. The runbook and the device's storage layout are in the [retroid-sync skill](../../.claude/skills/retroid-sync/SKILL.md)                                                                                                                   |

## Notes

| Constraint                           | Detail                                                                                                                                                                                                                                                                                                                                                                                                            |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `vars/main.yml` is not host-settable | Role vars outrank `host_vars`. It holds the canonical RetroArch data (`games_retroarch_systems`, `..._required_settings`, `..._core_overrides`, `..._core_options`, `..._controllers`), derived paths, upstream pins, flatpak sandbox grants and fact-derived values                                                                                                                                              |
| Override the source value            | `syncretroid` reads `vars/main.yml` directly and resolves no inventory, so a `host_vars` override of a derived value reaches the desktops but not the handheld. Override the default it derives from                                                                                                                                                                                                              |
| Dicts are replaced                   | Ansible replaces a dict instead of merging it, so a `host_vars` override of a dict must restate the whole value. `games_retroarch_extra_settings` is the one dict combined key by key, for settings a host adds                                                                                                                                                                                                   |
| Flatpak sets                         | `games_flatpak_common` is every host's set, and the `games_install_*` flags add the optional ones. `games_flatpak_apps` in `vars/` combines them for the tasks to install, extend and override. `host_vars` sets the flag, and the application ID stays in the role                                                                                                                                               |
| A flag turned off uninstalls         | Turning a `games_install_*` flatpak flag off uninstalls the application, its permission override and any runtime left unused, and keeps its `~/.var/app` data                                                                                                                                                                                                                                                     |
| Flatpak overrides are written whole  | `flatpak_override.yml` resets each override, then applies the role's grants, so a manual `flatpak override --user` edit is lost on the next run. BedrockOnLinux's comes from `bedrock.yml`, and Lutris's from `flatpak.yml` under both the flatpak and lutris tags. Each launcher's PATH is its manifest's with the helper directories first; BedrockOnLinux's manifest sets none, so it uses the runtime default |
| No dependencies                      | The role installs `flatpak` and adds the flathub remote for `games_user` itself                                                                                                                                                                                                                                                                                                                                   |

## Setup

1. Set the per-host [variables](#variables) in `host_vars`.
1. In Battle.net, set "When I launch a game" to exit, or its window stays open behind the game.
1. In BedrockOnLinux, clear the "Gamescope arguments" setting.
1. Make the library's thumbnail directory setgid and owned by the library's group.

## Operations

```bash
# Read a new pad's indices from its autoconfig profile, then add it to games_retroarch_controllers
flatpak run --command=grep org.libretro.RetroArch -E '^input_(r_y_minus_axis|r_y_plus_axis|l3_btn|r3_btn)' \
  "/app/share/libretro/autoconfig/udev/Microsoft_X-Box_Series_XS_pad.cfg"

# List which cores support rewind and preemptive frames
grep savestate_features <info_dir>/*_libretro.info

# Check for a game window on gamescope's nested display
DISPLAY=:1 xwininfo -root -children

# Take a screenshot from the running gamescope
flatpak run --command=/usr/lib/extensions/vulkan/gamescope/bin/gamescopectl \
  --env=GAMESCOPE_WAYLAND_DISPLAY=gamescope-0 <app-id> screenshot <path>

# Read the World of Warcraft launcher's log
less ~/.local/state/lutris-launch-game/world-of-warcraft.log
```
