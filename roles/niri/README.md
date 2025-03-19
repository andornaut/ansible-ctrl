# niri

* [Wayland ArchWiki](https://wiki.archlinux.org/title/Wayland#Configuration_file)

## Applications

* [brightnessctl](https://github.com/Hummer12007/brightnessctl) - A program to read and control device brightness
* [nwg-look](https://github.com/nwg-piotr/nwg-look) - GTK3 settings editor
* [wl-clip-persist](https://github.com/Linus789/wl-clip-persist)

## How to run X11 applications

e.g. `xwayland-run -- flatpak run com.valvesoftware.Steam`

Edit `.local/share/flatpak/exports/share/applications/com.valvesoftware.Steam.desktop`:

```ini
[Desktop Entry]
Name=Steam
# ...
Exec=xwayland-run -- /usr/bin/flatpak run --branch=stable --arch=x86_64 --command=/app/bin/steam --file-forwarding com.
```

### Greeter / Login Manager / Session Manager

* <https://git.sr.ht/%7Ekennylevinsen/greetd>
* <https://github.com/apognu/tuigreet>
* <https://github.com/Vladimir-csp/uwsm>

## TODO

### ibus warning session start

> ibus should be called from the desktop session in wayland

* [Reddit: disable panel](https://www.reddit.com/r/archlinux/comments/18trdk1/ibuswayland_error_no_input_method_global/ki2nf22/)

```bash
ibus-daemon -d --panel disable
```

### Steam doesn't start

```text
steam.sh[2]: Error: The unofficial Steam Flatpak app requires a correctly-configured desktop
session, which must provide the DISPLAY environment variable to the
D-Bus session bus activation environment.

On systems that use systemd --user, the DISPLAY environment variable must
also be present in the systemd --user activation environment.

This is usually achieved by running:

    dbus-update-activation-environment DISPLAY

during desktop environment startup.

For more details, please see:
https://github.com/ValveSoftware/steam-for-linux/issues/10554
```
