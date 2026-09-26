# ansible-role-games

Installs gaming apt packages and flatpaks on Ubuntu, and configures RetroArch for the ROM library.

## Usage

```bash
make games
make games -- --tags flatpak
make games -- --tags retroarch
```

## Tags

| Tag         | Description                                                                                                                                   |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| app-entries | Desktop entry overrides from `games_app_entry_overrides`, as in the [desktop](../desktop/README.md) role                                      |
| apt         | Native gaming packages                                                                                                                        |
| bedrock     | Minecraft Bedrock launcher and its desktop entry: [Minecraft (Bedrock)](#minecraft-bedrock)                                                   |
| flatpak     | Flatpak runtime, flathub remote, applications, extensions and overrides                                                                       |
| gamemode    | `/etc/gamemode.ini` and `gamemode` group membership: [GameMode](#gamemode)                                                                    |
| heroic      | Heroic install path and the store token-refresh timer                                                                                         |
| lutris      | Lutris default install path, gamescope settings, `DXVK_HUD=0` for every game, the launcher and the World of Warcraft entry: [Lutris](#lutris) |
| retroarch   | Libretro cores, BIOS, settings, per-core overrides, playlists and thumbnails: [RetroArch](#retroarch)                                         |
| retroid     | `syncretroid`, the handheld sync command, installed on the controller: [Handheld sync](#handheld-sync-retroid-pocket-flip-2)                  |

## Variables

Host-settable values are in [defaults/main.yml](./defaults/main.yml), each commented. [vars/main.yml](./vars/main.yml)
is not host-settable (see [Notes](#notes)).

Site data the role cannot detect. The play asserts each one, because a wrong value produces no error:

| Variable                                            | Purpose                                                                                                                                                |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `games_retroarch_library_dir`                       | Where the host mounts the ROM library. Also asserted mounted: an unmounted share looks empty                                                           |
| `games_retroarch_controller`                        | A key of `games_retroarch_controllers`. Bindings are physical device indices, so a wrong pad binds wrong buttons. [Operations](#operations) reads them |
| `games_retroarch_video_refresh_rate`                | The panel's rate, as RetroArch's "Estimate Screen Refresh Rate" reports it. A wrong value is heard as audio drift                                      |
| `games_gamescope_resolution`                        | The panel's mode as WIDTHxHEIGHT (`xrandr --current`). Required when `games_gamescope_enabled` is on                                                   |
| `games_retroid_library_dir`, `games_retroid_serial` | Rendered into `syncretroid`. Required when `games_install_retroid_sync` is on                                                                          |

## Installed files

| Path                                                            | Purpose                                                                          |
| --------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `/etc/gamemode.ini`                                             | GameMode settings                                                                |
| `/etc/udev/rules.d/70-ansible-role-games-retroarch-input.rules` | Mouse and keyboard read access for RetroArch                                     |
| `/etc/modules-load.d/ntsync.conf`                               | Loads `ntsync` at boot where the kernel ships it                                 |
| `/usr/local/bin/lutris-launch-game`                             | Lutris game launcher, [files/lutris-launch-game.py](files/lutris-launch-game.py) |
| `/usr/local/bin/syncretroid`                                    | Handheld sync wrapper, on the controller                                         |
| `~/.local/bin/world-of-warcraft-launch.sh`                      | World of Warcraft desktop entry's command                                        |
| `~/.local/bin/minecraft-bedrock-launch.sh`                      | Launches Minecraft (Bedrock), or focuses its window if already running           |
| `~/.local/bin/heroic-refresh-tokens`                            | Refreshes Heroic's store tokens, run by `heroic-token-refresh.timer`             |
| `~/.local/share/gamescope-helpers`                              | The gamescope wrapper                                                            |
| `~/.local/share/bol-helpers`                                    | A vendored xrandr for BedrockOnLinux                                             |
| `~/.local/state/lutris-launch-game/<slug>.log`                  | Launcher log                                                                     |

## Gamescope

`games_gamescope_enabled` runs Lutris games and Minecraft (Bedrock) inside gamescope, for games that do not set the
fullscreen state themselves and so have GNOME's top bar and dock drawn over them. It costs about one frame of
latency, and works on X11 and Wayland. Off by default. With the flag off, Lutris's own gamescope settings are left
alone.

Both launchers run the game under umu, where the flatpak portal resets `DISPLAY` and `WAYLAND_DISPLAY` to the
host's, so plain gamescope presents nothing (`Failed to get Xwayland server id` on X11, `Hooking has failed
somewhere!` on Wayland). The role puts a wrapper first on each sandbox's PATH that restores both; each file's header
comment says how.

| Constraint                     | Detail                                                                                                                                                                                       |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1280x720 window                | gamescope's default output size. The game runs but is not visible. `games_gamescope_resolution` sets the size, asserted rather than probed: a run without a logged-in session cannot read it |
| Keyboard map                   | The nested server takes its keymap from `games_gamescope_xkb_options`, not the session. A running game keeps the map it started with                                                         |
| BedrockOnLinux's own setting   | Its "Gamescope arguments" setting outranks the role's, and `0`, `off` or `false` there disables gamescope. Clear it in the launcher's GUI                                                    |
| `/proc` shows the host display | `/proc/<pid>/environ` shows the host's `DISPLAY` even when the game is on gamescope's. Check the window on gamescope's display instead ([Operations](#operations))                           |
| Screenshots                    | `import -window root` captures a fullscreen Vulkan window as black. Use gamescope's own ([Operations](#operations)), to a path inside `~/.var/app/<app-id>/data`                             |
| Log noise                      | `[gamescope-brokey]` is the flatpak's binary name, and `Starting headless backend` is the nested server, not the output backend. Neither indicates a fault                                   |

## GameMode

`games_gamemode_inhibit_screensaver` is false, so `gamemoderun` holds no screensaver inhibitor and GNOME can blank
and suspend during play. Tiling sessions have no `org.freedesktop.ScreenSaver`, so it has no effect there.

| Constraint                        | Detail                                                                                                                                              |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| User file wins                    | `~/.config/gamemode.ini` overrides `/etc/gamemode.ini`                                                                                              |
| Helpers need the `gamemode` group | Without it the daemon applies no governor, pinning or split-lock change and logs `Not authorized`. The tag adds `games_gamemode_users`              |
| The grant is account-wide         | Any process of a group member can run the root helpers without a prompt, and a change made outside the daemon is never reverted                     |
| Host-wide effect                  | While any game is registered, every core runs the `performance` governor and split-lock mitigation is off                                           |
| A crashed daemon keeps game state | Restore values are held in memory only. A replacement daemon takes the game-time values as its baseline                                             |
| Lutris games                      | Host-wide settings apply, but per-process ones (ioprio, pinning) do not reach the game                                                              |
| The screen still does not blank   | The game holds its own inhibitor. The limit above that is `desktop_idle_backstop_minutes` in the [desktop role](../desktop/README.md#idle-backstop) |

## RetroArch

**Close RetroArch before running the play.** It rewrites `retroarch.cfg` and its core options on exit, overwriting
what the play set. The `retroarch` tag asserts it is not running.

| Owned                                     | Detail                                                                                                                                                                                                 |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `retroarch.cfg`, per key                  | Only the keys in `games_retroarch_required_settings`. Other settings changed in the app persist                                                                                                        |
| The cores directory                       | From the nightly buildbot, refetched every run. The set is the desktop (x64) column of the [til notes](https://github.com/andornaut/til/blob/main/docs/retro-games.md#cores). Unused cores are removed |
| The BIOS set                              | Copied from the library into RetroArch's `system/`                                                                                                                                                     |
| The playlists                             | Generated from the library, not scanned in the app, so a new ROM needs a rerun of the `retroarch` tag                                                                                                  |
| Per-core overrides and core options       | Under `config/<library_name>/`, the name the core reports at runtime. Core options are enforced per key                                                                                                |
| The shared thumbnail cache in the library | The only RetroArch output hosts share. Only a host whose mount is writable downloads into it. The directory must already exist                                                                         |
| A udev input rule                         | Session read access to mice and keyboards, which `input_driver = udev` needs for the menu pointer and lightgun. It also hides an idle KVM virtual HID that would take mouse slot 0                     |

| Constraint                        | Detail                                                                                                                                                                                                      |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| The library can be read-only      | Every writable path (saves, states, `system/`, cache) stays under `~/.var/app/org.libretro.RetroArch/config/retroarch`                                                                                      |
| Swapping a core orphans its saves | Saves and states are keyed by `library_name`. States cannot migrate; battery saves only within an emulator family. Move battery saves by hand                                                               |
| Zip entries                       | A `.zip` is listed by its own path, so RetroArch does not open every archive over the network mount                                                                                                         |
| Multi-disc games                  | Cores that read `.m3u` get automatic disc swap. 3DO and GameCube entries point at disc 1                                                                                                                    |
| Read capabilities from the build  | Rewind and preemptive frames come from the `.info` file ([Operations](#operations)). Core options are undocumented: read them from the built core with `strings`                                            |
| ParaLLEl                          | Needs its `rdp-plugin` option set to `parallel` and the `video_driver` override set to vulkan together                                                                                                      |
| Thumbnail directory permissions   | Must be setgid and in the library's group, or the share does not serve what RetroArch creates. The play cannot check this                                                                                   |
| VRR                               | Set `vrr_runloop_enable` in `games_retroarch_extra_settings` on a VRR panel, and enable VRR for the display (compositor setting, or `Option "VariableRefresh"` under X11). On a fixed-refresh panel use BFI |
| Helper scripts                    | Run by hand to debug one stage: [files/README.md](./files/README.md)                                                                                                                                        |

## Minecraft (Bedrock)

BedrockOnLinux, installed from its release flatpak bundle, with a desktop entry that launches the game directly.
`ntsync` is loaded where the kernel ships it: Wine 11 has no other fast synchronization path.

## Lutris

Where Battle.net's prefix contains World of Warcraft, the `lutris` tag registers the game as its own Lutris entry
and installs a desktop entry that launches it without the Lutris window. The client lists the entry after its next
start.

| Constraint                           | Detail                                                                                                                                                                                                   |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Launched through Battle.net          | No password or authenticator prompt, but Battle.net must be logged in                                                                                                                                    |
| Configuration copied from Battle.net | Edit Battle.net's settings in the client. Changes to the World of Warcraft entry are overwritten by the next run                                                                                         |
| Not registered                       | An unregistered Battle.net, or a prefix without `_retail_/Wow.exe`, produces a warning                                                                                                                   |
| Nothing is removed                   | Uninstalling the game leaves the entry. Delete it in the client                                                                                                                                          |
| Stale prefix                         | Lutris leaves the prefix running after the game stops, which breaks the next launch. The desktop entry clears it (or hands the launch to it without gamescope); a launch from the Lutris window does not |
| Shared with Battle.net               | Clearing the prefix also closes a Battle.net window left open                                                                                                                                            |
| Second click                         | Reports the game as already running, or waits up to thirty seconds for a launch in progress                                                                                                              |
| Slow first launch                    | The first launch after a GE-Proton release downloads it first; the banner says so                                                                                                                        |
| Log                                  | `~/.local/state/lutris-launch-game/<slug>.log`. Read it first when a launch does nothing                                                                                                                 |

## Handheld sync (Retroid Pocket Flip 2)

[files/retroid/](./files/retroid/) copies this role's RetroArch configuration to a Retroid Pocket Flip 2, which
Ansible cannot reach. [files/retroid/README.md](./files/retroid/README.md) covers the device side, and the
[retroid-sync skill](../../.claude/skills/retroid-sync/SKILL.md) the runbook. No playbook runs the sync.

The `retroid` tag installs `/usr/local/bin/syncretroid` on the controller, where the handheld is plugged in. It runs
the script from this checkout, so an edit to the script or its data applies without rerunning the tag. Rerun it
when the checkout moves or `games_retroid_library_dir` or `games_retroid_serial` changes.

## Notes

| Constraint                           | Detail                                                                                                                                         |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `vars/main.yml` is not host-settable | Role vars outrank `host_vars`. It holds the canonical RetroArch data, paths and application IDs                                                |
| The handheld reads `vars/` only      | A per-host setting (`games_retroarch_extra_settings`, the refresh rate, the controller) reaches the desktops only                              |
| Dicts are replaced                   | A `host_vars` override of a dict must restate the whole value. `games_retroarch_extra_settings` is the exception, combined key by key          |
| A flag turned off uninstalls         | Turning a `games_install_*` flatpak flag off uninstalls the application, its override and unused runtimes, and keeps its `~/.var/app` data     |
| Flatpak overrides are written whole  | A manual `flatpak override --user` edit is lost on the next run                                                                                |
| Encrypted home must be mounted       | The run fails before any change if `games_user`'s ecryptfs home is locked. Log in as `games_user`, or run `ecryptfs-mount-private`, and re-run |

## Setup

1. Set the per-host [variables](#variables) in `host_vars`.
1. In Battle.net, set "When I launch a game" to exit, or its window stays open behind the game.
1. In BedrockOnLinux, clear the "Gamescope arguments" setting.
1. Create the library's thumbnail directory, setgid and owned by the library's group. The role never creates it.

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
