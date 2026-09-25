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

| Constraint                           | Detail                                                                                                                                                                                                                                                                                                                               |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Pinned hypr stack                    | `niri_hypr_versions` in [vars/main.yml](./vars/main.yml) pins each hyprwm component at the newest release gcc-14 builds. Later hyprutils needs gcc-15's libstdc++, and later hyprpaper needs hyprtoolkit and hyprwire. An unpinned component builds its latest release                                                               |
| gcc-14 for the builds only           | The source builds get `CC=gcc-14 CXX=g++-14`; the host's default compiler is unchanged, so DKMS modules keep building with the kernel's                                                                                                                                                                                              |
| `niri.service` is not enabled        | It has no `[Install]` section; `niri-session` starts it                                                                                                                                                                                                                                                                              |
| User units are enabled by symlink    | `hypridle.service` and `hyprpaper.service` are linked into `niri_user`'s `~/.config/systemd/user/<target>.wants/` by [tasks/enable_user_unit.yml](./tasks/enable_user_unit.yml), and started only when the target that wants them is active. On a host where `niri_user` has no graphical session, the unit starts at the next login |
| Install target is read from the unit | These units come from upstream tarballs, so the target comes from the unit's own `[Install]` section. A unit that names none fails the run                                                                                                                                                                                           |
| Locked encrypted home                | Writes into `niri_user`'s home are skipped while it is not mounted: an encrypted home is a mount point that `getent` reports either way. See [desktop](../desktop/README.md) for the same check                                                                                                                                      |
| Wayland-only                         | This role owns only the Wayland-only utilities. X11 counterparts are in [bspwm](../bspwm/); tools both sessions share are in [desktop](../desktop/)                                                                                                                                                                                  |
| X11 applications                     | niri starts `xwayland-satellite` from `$PATH` when an X11 client first connects and sets `DISPLAY` for the session, so it has no unit. `xwayland-run` is installed for an application that needs an X server of its own                                                                                                              |
