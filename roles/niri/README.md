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

| Tag | Description |
| --- | --- |
| [hypr](https://hypr.land/) | Hyprland ecosystem tools (hyprlock, hypridle, hyprpaper) |
| [niri](https://github.com/niri-wm/niri) | Wayland compositor |
| [wayland](https://wayland.freedesktop.org/) | Wayland packages and protocols, and [xwayland-satellite](https://github.com/Supreeeme/xwayland-satellite) |

Each source build also carries a tag of its own, for rebuilding one component without the rest: `packages`,
`libsdbus`, `xwayland`, and one per Hyprland component (`hyprutils`, `hyprlang`, `hyprgraphics`, `hyprscanner`,
`hypridle`, `hyprlock`, `hyprpaper`). The first four Hyprland ones are build dependencies of the last three.

## Variables

See [defaults/main.yml](./defaults/main.yml).

## Notes

- Owns only the Wayland-only utilities. X11 counterparts live in [bspwm](../bspwm/); tools both sessions share
  live in [desktop](../desktop/).
- X11 applications such as Steam need `xwayland-run` in their desktop entry:

  ```ini
  [Desktop Entry]
  Name=Steam
  Exec=xwayland-run -- /usr/bin/flatpak run --branch=stable --arch=x86_64 --command=/app/bin/steam --file-forwarding com.valvesoftware.Steam
  ```
