# ansible-role-desktop

Configures a Linux desktop environment with common applications on Ubuntu.

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
| display-manager | Display manager ([lemurs](https://github.com/coastalwhite/lemurs) or [ly](https://github.com/fairyglade/ly)) |
| [dunst](https://dunst-project.org/) | Notification daemon (built from source) |
| [eww](https://github.com/elkowar/eww) | Widget daemon (built with Cargo) |
| [firefox](https://www.mozilla.org/firefox/) | Web browser (PPA or Flatpak) |
| [flatpak](https://flatpak.org/) | Flatpak runtime and Flathub apps |
| fonts | System fonts (Hack, DejaVu, Source Code Pro, etc.) |
| [grub](https://www.gnu.org/software/grub/) | Bootloader settings |
| [insync](https://www.insynchq.com/) | Google Drive sync client |
| [lact](https://github.com/ilya-zlobintsev/LACT) | AMD GPU control utility |
| [pavolume](https://github.com/andornaut/pavolume) | PulseAudio volume controller |
| [rofi](https://github.com/lbonn/rofi) | Application launcher (Wayland fork, built from source) |

## Variables

See [defaults/main.yml](./defaults/main.yml).
