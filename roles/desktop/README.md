# ansible-role-desktop

Configures a Linux desktop environment with common applications on Ubuntu.

Set `desktop_environment` per host to choose the environment:

- `tiling` (default): bspwm/niri window managers with a lemurs/ly display manager, plus dunst, eww, rofi, and pavolume. Pair with the `bspwm` or `niri` role.
- `gnome`: GNOME Shell with gdm3 (installs `ubuntu-desktop-minimal` and the Xorg session), skipping the WM-specific tools.

Applications common to both (browsers, flatpak, fonts, GRUB, LACT, etc.) are installed regardless.

## Usage

```bash
make desktop

ansible-playbook --ask-become-pass desktop.yml --tags firefox
```

## Tags

| Tag | Description |
| --- | --- |
| [alacritty](https://alacritty.org/) | Terminal emulator |
| [chrome](https://www.google.com/chrome/) | Web browser |
| [dconf](https://wiki.gnome.org/Projects/dconf) | GNOME settings (keyboard layout, input sources) |
| display-manager | Display manager ([lemurs](https://github.com/coastalwhite/lemurs) or [ly](https://github.com/fairyglade/ly)), tiling only |
| gnome | GNOME Shell + gdm3 (`ubuntu-desktop-minimal`), gnome only |
| [dunst](https://dunst-project.org/) | Notification daemon (built from source), tiling only |
| [eww](https://github.com/elkowar/eww) | Widget daemon (built with Cargo), tiling only |
| [firefox](https://www.mozilla.org/firefox/) | Web browser (PPA or Flatpak) |
| [flatpak](https://flatpak.org/) | Flatpak runtime and Flathub apps |
| fonts | System fonts (Hack, DejaVu, Source Code Pro, etc.) |
| [grub](https://www.gnu.org/software/grub/) | Bootloader settings |
| [insync](https://www.insynchq.com/) | Google Drive sync client |
| [lact](https://github.com/ilya-zlobintsev/LACT) | AMD GPU control utility |
| [pavolume](https://github.com/andornaut/pavolume) | PulseAudio volume controller, tiling only |
| [rofi](https://github.com/lbonn/rofi) | Application launcher (Wayland fork, built from source), tiling only |

## Variables

See [defaults/main.yml](./defaults/main.yml).
