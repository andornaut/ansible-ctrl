# ansible-role-niri

Installs and configures [niri](https://github.com/YaLTeR/niri) Wayland compositor on Ubuntu.

- [sway-services](https://github.com/xdbob/sway-services)

## Usage

```bash
make niri

ansible-playbook --ask-become-pass niri.yml --tags hypr
ansible-playbook --ask-become-pass niri.yml --tags xwayland
```

## Variables

See [defaults/main.yml](./defaults/main.yml).

## Running X11 Applications

For X11 applications like Steam, modify the desktop entry:

```ini
[Desktop Entry]
Name=Steam
Exec=xwayland-run -- /usr/bin/flatpak run --branch=stable --arch=x86_64 --command=/app/bin/steam --file-forwarding com.valvesoftware.Steam
```
