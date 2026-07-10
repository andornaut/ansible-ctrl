# ansible-role-niri

Installs the [niri](https://github.com/YaLTeR/niri) Wayland compositor, the Hyprland ecosystem tools, and the
Wayland utilities its session requires, on Ubuntu.

## Usage

Applied by `desktop.yml` when `desktop_environment == "niri"`.

```bash
make desktop

ansible-playbook --ask-become-pass desktop.yml --tags niri
ansible-playbook --ask-become-pass desktop.yml --tags hypr
```

## Tags

| Tag | Description |
| --- | --- |
| [hypr](https://hyprland.org/) | Hyprland ecosystem tools (hyprlock, hypridle, hyprpaper, etc.) |
| [niri](https://github.com/YaLTeR/niri) | Wayland compositor |
| [wayland](https://wayland.freedesktop.org/) | Wayland packages (brightnessctl, grim, slurp, wl-clipboard), protocols, and [xwayland-satellite](https://github.com/Supreeeme/xwayland-satellite) |

## Variables

See [defaults/main.yml](./defaults/main.yml).

## Notes

- This role owns only the Wayland-only utilities (brightnessctl, grim, slurp, wl-clipboard). Their X11
  counterparts belong to the [bspwm](../bspwm/) role, and tools both sessions share live in the
  [desktop](../desktop/) role.
- X11 applications such as Steam need `xwayland-run` in their desktop entry:

  ```ini
  [Desktop Entry]
  Name=Steam
  Exec=xwayland-run -- /usr/bin/flatpak run --branch=stable --arch=x86_64 --command=/app/bin/steam --file-forwarding com.valvesoftware.Steam
  ```
