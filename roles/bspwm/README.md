# ansible-role-bspwm

Installs [BSPWM](https://github.com/baskerville/bspwm) and related desktop utilities on Ubuntu.

## Usage

Applied by the `desktop` playbook when `desktop_environment == "bspwm"`, or run the role directly by tag:

```bash
ansible-playbook --ask-become-pass desktop.yml --tags bspwm
```

## Variables

See [defaults/main.yml](./defaults/main.yml).

## Configuration Files

- `~/.config/bspwm/bspwmrc` - BSPWM configuration
- `~/.config/sxhkd/sxhkdrc` - Keyboard shortcuts
