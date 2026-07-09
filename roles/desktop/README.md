# ansible-role-desktop

Configures a Linux desktop environment with common applications on Ubuntu.

Set `desktop_environment` per host to choose the environment:

- `niri` or `bspwm`: the named tiling window manager (applied by `desktop.yml`) with a lemurs/ly display manager, plus dunst, eww, rofi, and pavolume.
- `gnome`: GNOME Shell with gdm3 (installs `ubuntu-desktop-minimal`), skipping the WM-specific tools. GNOME 49+ ships a Wayland-only session, so no Xorg server is installed; legacy X11 apps run under XWayland, which GNOME pulls in.

Applications common to all (browsers, flatpak, fonts, GRUB, LACT, etc.) are installed regardless.

On tiling hosts this role also installs the session utilities a window manager does not provide for itself (blueman, lxappearance, network-manager-gnome, policykit-1-gnome) and the X11 tools both tiling sessions use, since niri runs them as XWayland clients (feh, suckless-tools, wmctrl, xclip, xinput, xsel). Only the tools with a true Wayland replacement belong to the [bspwm](../bspwm/) role (X11) and the [niri](../niri/) role (Wayland).

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
| [coolercontrol](https://gitlab.com/coolercontrol/coolercontrol) | Fan and pump curve control (Cloudsmith apt repo) |
| [dconf](https://wiki.gnome.org/Projects/dconf) | GNOME settings (keyboard layout, input sources) |
| display-manager | Display manager ([lemurs](https://github.com/coastalwhite/lemurs) or [ly](https://github.com/fairyglade/ly)), tiling only |
| [dunst](https://dunst-project.org/) | Notification daemon (built from source), tiling only |
| [eww](https://github.com/elkowar/eww) | Widget daemon (built with Cargo), tiling only |
| [file-roller](https://gitlab.gnome.org/GNOME/file-roller) | Default handler for archive MIME types |
| [firefox](https://www.mozilla.org/firefox/) | Web browser (Flathub flatpak, or the Mozilla apt repo when `desktop_install_firefox_apt`) |
| [flatpak](https://flatpak.org/) | Flatpak runtime and Flathub apps |
| fonts | System fonts (Hack, DejaVu, Source Code Pro, etc.) |
| gnome | GNOME Shell + gdm3 (`ubuntu-desktop-minimal`), gnome only |
| [grub](https://www.gnu.org/software/grub/) | Bootloader settings |
| [insync](https://www.insynchq.com/) | Google Drive sync client (`desktop_install_insync`) |
| [it87](https://github.com/frankcrawford/it87) | DKMS Super I/O driver for ITE chips on Gigabyte AM5 boards (`desktop_install_it87`) |
| [lact](https://github.com/ilya-zlobintsev/LACT) | AMD GPU control utility |
| [nct6687d](https://github.com/Fred78290/nct6687d) | DKMS Super I/O driver for Nuvoton chips on MSI boards (`desktop_install_nct6687d`) |
| parental-controls | [malcontent](https://gitlab.freedesktop.org/pwithnall/malcontent) OARS filter and Chrome SafeSearch policies (`desktop_install_parental_controls`) |
| [pavolume](https://github.com/andornaut/pavolume) | PulseAudio volume controller, tiling only |
| [rofi](https://github.com/lbonn/rofi) | Application launcher (Wayland fork, built from source), tiling only |

Tags naming a `desktop_install_*` variable are gated on that flag, which defaults to `false`: the tag alone
runs nothing. The Super I/O drivers expose the pwm/fan hwmon that CoolerControl manages; enable the one
matching the board's chip.

`desktop_default_browser` (`firefox` or `google-chrome`) selects which browser `xdg-settings` marks as the
default handler.

## Variables

See [defaults/main.yml](./defaults/main.yml).

The `ly` display manager is built with Zig, which is downloaded from `desktop_zig_mirror` rather than from ziglang.org, whose donated bandwidth makes the origin download take about 20 minutes. Set it to a host listed in [community-mirrors.txt](https://ziglang.org/download/community-mirrors.txt); the archive is checksummed against the shasum the origin publishes.
