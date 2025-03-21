# ansible-role-bspwm

An [Ansible](https://www.ansible.com/) role that installs [BSPWM](https://github.com/baskerville/bspwm) (a tiling window manager) and related desktop utilities on Ubuntu.

## Overview

BSPWM (Binary Space Partitioning Window Manager) is a minimal tiling window manager that represents windows as the leaves of a binary tree. This role automates its installation and configuration along with complementary tools.

## Features

- BSPWM window manager installation
- Efficient keyboard-driven window management
- Multiple monitor support
- Configurable window rules and behaviors
- Integration with sxhkd for keybindings
- Minimal resource footprint

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
    - role: bspwm
```

### Configuration Files

After installation, the following configuration files are available:

- `~/.config/bspwm/bspwmrc` - BSPWM configuration
- `~/.config/sxhkd/sxhkdrc` - Keyboard shortcuts

## License

MIT License. See [LICENSE](../../LICENSE) for full details.
