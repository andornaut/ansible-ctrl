# ansible-role-niri

An [Ansible](https://www.ansible.com/) role that installs and configures [niri](https://github.com/YaLTeR/niri), a Wayland compositor, on Ubuntu.

* [sway-services](https://github.com/xdbob/sway-services)

## Overview

This role automates the installation and configuration of niri, a Wayland compositor focused on providing a simple and efficient desktop environment.

## Features

- Niri Wayland compositor installation
- X11 application compatibility via XWayland
- IBus input method configuration
- System-wide and per-user configuration

## Requirements

- Ansible 2.9 or higher
- Ubuntu operating system

## Role Variables

See [default values](./defaults/main.yml).

## Usage

1. Include this role in your playbook
2. Configure the required variables
3. Run your playbook

```yaml
- hosts: workstations
  roles:
    - role: niri
```

### Running X11 Applications

For X11 applications like Steam, modify the desktop entry:

```ini
[Desktop Entry]
Name=Steam
Exec=xwayland-run -- /usr/bin/flatpak run --branch=stable --arch=x86_64 --command=/app/bin/steam --file-forwarding com.valvesoftware.Steam
```

## License

MIT License. See [LICENSE](../../LICENSE) for full details.
