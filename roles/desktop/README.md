# ansible-role-desktop

Installs a Linux desktop environment and common applications on Ubuntu.

## Usage

```bash
make desktop
make desktop -- --tags browser
```

`desktop.yml` applies this role, then [bspwm](../bspwm/README.md) or [niri](../niri/README.md) per the host's
`desktop_environment`.

A bspwm or niri host must be in the `dev` group and have had `make dev -- --limit <host>` run first: eww and niri
build with the dev role's Rust, nwg-drawer with its Go.

## Tags

Tags marked _tiling_ are skipped when `desktop_environment` is `gnome`.

| Tag                                                             | Description                                                                                                                                                       |
| --------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [alacritty](https://alacritty.org/)                             | Terminal emulator                                                                                                                                                 |
| app-grid                                                        | GNOME app grid folders from `desktop_app_grid_folders`. gnome only                                                                                                |
| app-entries                                                     | Desktop entry overrides from `desktop_app_entry_overrides`, which hide an entry or set its categories                                                             |
| browser                                                         | [Google Chrome](https://www.google.com/chrome/) and [Firefox](https://www.firefox.com/), and `desktop_default_browser` as the default                             |
| [coolercontrol](https://gitlab.com/coolercontrol/coolercontrol) | Fan and pump curve control                                                                                                                                        |
| [dconf](https://wiki.gnome.org/Projects/dconf)                  | GNOME keyboard layout and input sources, locked for every account. gnome only                                                                                     |
| display-manager                                                 | [lemurs](https://github.com/coastalwhite/lemurs) or [ly](https://github.com/fairyglade/ly) on a tiling host, gdm3 on gnome. Every other display manager is masked |
| [dunst](https://dunst-project.org/)                             | Notification daemon, built from source, _tiling_                                                                                                                  |
| [eww](https://github.com/elkowar/eww)                           | Widget daemon, _tiling_                                                                                                                                           |
| [file-roller](https://gitlab.gnome.org/GNOME/file-roller)       | Default handler for archive MIME types                                                                                                                            |
| [flameshot](https://flameshot.org/)                             | Screenshot tool, tied to eww's tray, _tiling_. A gnome host installs the flatpak through `desktop_install_flameshot` instead                                      |
| [flatpak](https://flatpak.org/)                                 | Flatpak runtime and Flathub apps                                                                                                                                  |
| fonts                                                           | System fonts                                                                                                                                                      |
| gnome                                                           | GNOME Shell and gdm3, gnome only, and Power Off and Restart on the lock screen while another user has a session                                                   |
| [grub](https://www.gnu.org/software/grub/)                      | Bootloader settings                                                                                                                                               |
| idle                                                            | Screen blanking, locking, monitor power-off, idle suspend and the [idle backstop](#idle-backstop). Locked for every account under gnome                           |
| [insync](https://www.insynchq.com/)                             | Google Drive sync client (`desktop_install_insync`)                                                                                                               |
| [it87](https://github.com/frankcrawford/it87)                   | DKMS Super I/O driver for ITE chips on Gigabyte AM5 boards (`desktop_install_it87`)                                                                               |
| keyboard-configurator                                           | Grants the seat the raw HID interface of each keyboard in `desktop_keyboard_configurator_ids`, and its bootloaders; see [Notes](#notes)                           |
| [lact](https://github.com/ilya-zlobintsev/LACT)                 | AMD GPU control utility                                                                                                                                           |
| [nct6687d](https://github.com/Fred78290/nct6687d)               | DKMS Super I/O driver for Nuvoton chips on MSI boards (`desktop_install_nct6687d`)                                                                                |
| [nwg-drawer](https://github.com/nwg-piotr/nwg-drawer)           | Fullscreen application grid, built from source, _tiling_; see [Notes](#notes)                                                                                     |
| [openrgb](https://openrgb.org/)                                 | RGB lighting control (`desktop_install_openrgb`)                                                                                                                  |
| parental-controls                                               | [malcontent](https://gitlab.freedesktop.org/pwithnall/malcontent) app and web filters, and Chrome policies                                                        |
| [pavolume](https://github.com/andornaut/pavolume)               | PulseAudio volume controller, _tiling_                                                                                                                            |
| [rofi](https://github.com/lbonn/rofi)                           | Application launcher (Wayland fork, built from source), _tiling_                                                                                                  |
| theme                                                           | GTK themes, the GNOME colour scheme, and the flatpak theme override                                                                                               |
| usb-autosuspend                                                 | Turns USB autosuspend off for `desktop_usb_no_autosuspend_vendor_ids`                                                                                             |
| wireplumber                                                     | Per-node property overrides from `desktop_wireplumber_node_properties`                                                                                            |

## Variables

See [defaults/main.yml](./defaults/main.yml). The ones whose behaviour is not obvious from the name:

| Variable                                    | Purpose                                                                                                                                                                                                         |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `desktop_environment`                       | `bspwm`, `niri`, or `gnome`. Required                                                                                                                                                                           |
| `desktop_install_*`                         | Feature flags, all `false` by default except `firefox`. `parental_controls`, `firefox`, `it87`, `nct6687d` and the optional flatpaks undo an earlier run when turned off; a flatpak's `~/.var/app` data is kept |
| `desktop_screen_*_minutes`                  | Idle timeouts, in order: blank, lock, monitor power-off                                                                                                                                                         |
| `desktop_suspend_inactive_minutes`          | Idle suspend. Unset leaves the host's policy unchanged; 0 disables it                                                                                                                                           |
| `desktop_idle_backstop_minutes`             | Minutes without input after which the panel is powered down, whatever holds an idle inhibitor. Must be above `desktop_screen_blank_minutes`                                                                     |
| `desktop_xsecurelock_auth_background_color` | Tints the password dialog, so a tinted box means keystrokes reach the password field                                                                                                                            |
| `desktop_parental_controls_web_*`           | Web filter for `desktop_user`: filter type, filter lists, custom hostnames, safe search                                                                                                                         |
| `desktop_wireplumber_node_properties`       | Per-node WirePlumber overrides keyed by `node.name`: `audio.format` pins a device's sample format, `node.disabled` hides a node                                                                                 |
| `desktop_apt_pinned_packages`               | Apt packages purged and pinned because a flatpak provides the same application                                                                                                                                  |
| `desktop_app_grid_folders`                  | `{folder name: [.desktop ids]}` for the GNOME app grid. The map is the whole set: an unnamed folder is removed. An empty map leaves the shell's folders alone                                                   |
| `desktop_app_entry_overrides`               | `{<id>.desktop: {hidden: true} or {categories: [..]}}`. `desktop_app_entry_overrides_extra` (host_vars) adds a host's hand-installed ones                                                                       |

## Desktop environments

| Constraint            | Detail                                                                                                                                                 |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| gnome                 | GNOME Shell and gdm3, without the tiling tags. No Xorg server; X11 apps run under XWayland                                                             |
| Tiling hosts          | The _tiling_ tags plus the session tools both tiling sessions use. niri runs the X11 ones under XWayland                                               |
| Display manager       | A tiling host sets exactly one of `desktop_install_ly` and `desktop_install_lemurs`. A host can move between gnome and a tiling session                |
| Window manager roles  | Only tools with a per-protocol replacement belong to [bspwm](../bspwm/) (X11) or [niri](../niri/) (Wayland)                                            |
| User not logged in    | User units are enabled but not started; they start at `desktop_user`'s next graphical login                                                            |
| Locked encrypted home | The run fails before any change while `desktop_user`'s encrypted home is not mounted. Log in as that user or run `ecryptfs-mount-private`, then re-run |

## Idle, locking and suspend

The three `desktop_screen_*_minutes` timeouts are one policy applied per environment:

| Environment | Mechanism                   | Timeouts honoured      |
| ----------- | --------------------------- | ---------------------- |
| gnome       | dconf, system database      | blank, lock            |
| bspwm       | `xss-lock` and the X server | blank, lock, power-off |
| niri        | `hypridle`                  | lock, power-off        |

| Constraint                        | Detail                                                                                                                                                     |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| bspwm reads the timeouts at login | A change takes effect at the next login                                                                                                                    |
| Blanked is not locked             | Between blank and lock a keystroke wakes the screen and also reaches the focused window. Set the lock timeout equal to the blank timeout to close that gap |
| gnome policy is locked            | No account can change the idle or keyboard settings from Settings                                                                                          |
| bspwm suspend is host-wide        | An idle `ssh` login also delays suspend                                                                                                                    |
| niri value is in a shared dotfile | `.config/hypr/hypridle.conf` is a dotfiles symlink, so niri hosts must share one `desktop_suspend_inactive_minutes`                                        |
| Dangling dotfile links            | The run fails on a dangling dotfile link rather than replace it with a regular file                                                                        |

### Idle backstop

Any application can hold an idle inhibitor indefinitely, and games do for as long as they run, leaving a static
image on the panel. `desktop-idle-backstop.service` powers the panel down after `desktop_idle_backstop_minutes`
without input from the input devices, whatever holds an inhibitor:

| Environment | Powers the panel down with                             |
| ----------- | ------------------------------------------------------ |
| gnome       | `ddcutil setvcp d6 04`, then `d6 01` on the next input |
| bspwm       | `xset dpms force off`                                  |
| niri        | `niri msg action power-off-monitors`                   |

| Constraint              | Detail                                                                                                    |
| ----------------------- | --------------------------------------------------------------------------------------------------------- |
| Not input               | Joystick axis motion (stick drift) and key autorepeat. Touchpads and touchscreens count                   |
| gnome needs DDC/CI      | A monitor that does not accept `d6` 04 and 01 (`ddcutil capabilities`) cannot be backstopped              |
| Not bounded by suspend  | An inhibitor also defers idle suspend, so the backstop still fires when suspend cannot                    |
| Restarts in the journal | The backstop exits when it cannot read the idle time. Repeated restarts mean it is not enforcing anything |

## Parental controls

Web filtering is enforced by `nss-malcontent` in the name service switch, not the browser, and applies per user.

| Constraint                             | Detail                                                                                                                                                                                       |
| -------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Exact hostname matching                | No wildcards or subdomains. Lists must be plain newline-separated hostnames served over HTTPS; one malformed line keeps the previous list                                                    |
| Empty lists are rejected               | An empty allow list blocks everything, and an empty block list filters nothing                                                                                                               |
| Turning it off                         | With `desktop_install_parental_controls` false the filters and browser policies are cleared. Also remove the host's `desktop_parental_controls_*` settings, which the role asserts are unset |
| Firefox policies are host-wide         | `DisablePrivateBrowsing` and DoH off apply to every account on the host                                                                                                                      |
| Flatpak browsers bypass the web filter | A flatpak runtime does not read the host's `/etc/nsswitch.conf`. DNS filtering at the router covers them                                                                                     |
| Chrome policy directory                | Files in `/etc/opt/chrome/policies/managed/` that the role did not deploy are removed                                                                                                        |

## Notes

| Constraint                          | Detail                                                                                                                                               |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| systemd-networkd                    | Disabled unless netplan renders a link with it                                                                                                       |
| keyboard-configurator scope         | Only the raw HID interface is granted. A keyboard interface the user can open is one a game's Wine reads keys from, below every keymap and XKB remap |
| nwg-drawer                          | `pkill -USR1 -x nwg-drawer` toggles it; the sxhkd dotfile binds it. Its last button, Hobbies, holds every entry no other button matches              |
| Flatpak overrides are written whole | A manual `flatpak override --user` or Flatseal edit to an application this role manages is lost on the next run                                      |
| App entry overrides                 | A copy of the packaged entry with one field changed. The dev, games and hobbies roles use the same mechanism                                         |
| Source builds                       | eww and pavolume rebuild every run; the other source builds only on a new release                                                                    |
| lemurs                              | x86_64 only                                                                                                                                          |

## Operations

```bash
pkill -USR1 -x nwg-drawer      # Toggle the application grid
ddcutil capabilities           # Which d6 (power mode) values a monitor accepts
make desktop -- --tags idle    # Reapply the idle policy; bspwm picks it up at the next login
```
