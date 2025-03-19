# niri

* [Wayland ArchWiki](https://wiki.archlinux.org/title/Wayland#Configuration_file)

## Applications

* [brightnessctl](https://github.com/Hummer12007/brightnessctl) - A program to read and control device brightness
* [nwg-look](https://github.com/nwg-piotr/nwg-look) - GTK3 settings editor
* [wl-clip-persist](https://github.com/Linus789/wl-clip-persist)

## How-tos

### How to run X11 applications

e.g. `xwayland-run -- flatpak run com.valvesoftware.Steam`

Edit `.local/share/flatpak/exports/share/applications/com.valvesoftware.Steam.desktop`:

```ini
[Desktop Entry]
Name=Steam
# ...
Exec=xwayland-run -- /usr/bin/flatpak run --branch=stable --arch=x86_64 --command=/app/bin/steam --file-forwarding com.
```

### ibus warning notification at session start

> ibus should be called from the desktop session in wayland

Option 1: [Disable GTK panel](https://www.reddit.com/r/archlinux/comments/18trdk1/ibuswayland_error_no_input_method_global/ki2nf22/)

```bash
ibus-daemon -d --panel disable
```

Option 2: [Do not activate any IM](https://discuss.kde.org/t/ibus-issue-with-wayland/3680/12)

> Another solution is to run im-config → OK → Yes → do not activate any IM from im-config and use desktop default → OK and then reboot.
