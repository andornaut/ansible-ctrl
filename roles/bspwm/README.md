# ansible-role-bspwm

An [Ansible](https://www.ansible.com/) role that installs [BSPWM](https://github.com/baskerville/bspwm) (a tiling window manager) and other desktop environment related utilities on Ubuntu.

## Overview

BSPWM (Binary Space Partitioning Window Manager) is a minimal tiling window manager that represents windows as the leaves of a binary tree. It provides:

- Efficient keyboard-driven window management
- Support for multiple monitors
- Configurable window rules and behaviors
- Minimal resource usage
- Integration with sxhkd for keybindings

## Requirements

- Ansible 2.9 or newer
- Ubuntu Noble (24.04)

## Role Variables

See [default values](./defaults/main.yml).

## Configuration

After installation, the following configuration files are available:

- `~/.config/bspwm/bspwmrc` - BSPWM configuration
- `~/.config/sxhkd/sxhkdrc` - Keyboard shortcuts

## License

MIT
