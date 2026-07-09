# ansible-role-niri

Installs and configures the [niri](https://github.com/YaLTeR/niri) Wayland compositor, the Hyprland ecosystem tools, and the Wayland utilities used by the niri session on Ubuntu.

The Wayland-only utilities (brightnessctl, grim, slurp, wl-clipboard) live here rather than in the `desktop` role; their X11 counterparts (xbacklight, scrot) are installed by the [bspwm](../bspwm/) role. X11 tools with no Wayland replacement stay in the `desktop` role, because niri runs them as XWayland clients.

## Usage

Applied by the `desktop` playbook when `desktop_environment == "niri"`, or run the role directly by tag:

```bash
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

## Running X11 Applications

For X11 applications like Steam, modify the desktop entry:

```ini
[Desktop Entry]
Name=Steam
Exec=xwayland-run -- /usr/bin/flatpak run --branch=stable --arch=x86_64 --command=/app/bin/steam --file-forwarding com.valvesoftware.Steam
```
