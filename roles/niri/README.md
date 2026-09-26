# ansible-role-niri

Installs the [niri](https://github.com/niri-wm/niri) Wayland compositor, the Hyprland ecosystem tools, and the
Wayland utilities its session requires, on Ubuntu.

## Usage

Applied by `desktop.yml` when `desktop_environment == "niri"`.

```bash
make desktop
make desktop -- --tags niri
```

## Tags

| Tag                                                    | Description                                                                                               |
| ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------- |
| [hypr](https://hypr.land/)                             | Hyprland ecosystem tools (hyprlock, hypridle, hyprpaper)                                                  |
| [niri](https://github.com/niri-wm/niri)                | Everything in this role: `desktop.yml` tags the role `niri`                                               |
| [wayland](https://wayland.freedesktop.org/)            | Wayland packages and protocols, and [xwayland-satellite](https://github.com/Supreeeme/xwayland-satellite) |
| packages                                               | The apt build dependencies                                                                                |
| libsdbus                                               | sdbus-c++ build                                                                                           |
| xwayland                                               | xwayland-satellite build                                                                                  |
| hyprutils, hyprlang, hyprgraphics, hyprwayland-scanner | One Hyprland build dependency each, needed by hypridle, hyprlock and hyprpaper                            |
| hypridle, hyprlock, hyprpaper                          | One Hyprland component each                                                                               |

The wayland-scanner, wayland-protocols and hyprland-protocols builds have no tag of their own; `wayland` and `hypr`
reach them.

## Variables

See [defaults/main.yml](./defaults/main.yml).

## Notes

| Constraint                 | Detail                                                                                                                                                                   |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Pinned hypr stack          | `niri_hypr_versions` in [vars/main.yml](./vars/main.yml) pins each hyprwm component at the newest release gcc-14 builds. An unpinned component builds its latest release |
| gcc-14 for the builds only | The host's default compiler is unchanged, so DKMS modules keep building with the kernel's                                                                                |
| Rust                       | niri and xwayland-satellite build with `niri_user`'s `cargo`, from the [dev](../dev/README.md) role's `rust` tag                                                         |
| Rebuilt on every run       | hyprpaper and xwayland-satellite report no version; the other builds skip when the installed version is current                                                          |
| User not logged in         | `hypridle` and `hyprpaper` are enabled but not started; they start at the next graphical login                                                                           |
| Locked encrypted home      | The run fails before any change while `niri_user`'s encrypted home is not mounted. Log in as that user or run `ecryptfs-mount-private`, then re-run                      |
| Wayland-only               | X11 counterparts are in [bspwm](../bspwm/); shared tools are in [desktop](../desktop/)                                                                                   |
| X11 applications           | niri starts `xwayland-satellite` when an X11 client first connects. `xwayland-run` is installed for an application that needs an X server of its own                     |
