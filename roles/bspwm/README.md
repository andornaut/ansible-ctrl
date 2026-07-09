# ansible-role-bspwm

Installs [BSPWM](https://github.com/baskerville/bspwm) and the X11 utilities used by its session on Ubuntu.

BSPWM and the [baskerville](https://github.com/baskerville) tools listed in `bspwm_projects` are built from source into `/usr/local/bin`.

Only the X11 tools with a true Wayland replacement in the [niri](../niri/) role belong here: `scrot` (grim and slurp), `xautolock` (hypridle), `xbacklight` (brightnessctl), plus `dex` and `xorg`. Tools that both sessions share live in the [desktop](../desktop/) role.

## Usage

Applied by the `desktop` playbook when `desktop_environment == "bspwm"`, or run the role directly by tag:

```bash
ansible-playbook --ask-become-pass desktop.yml --tags bspwm
```

## Tags

| Tag | Description |
| --- | --- |
| bspwm | Everything in this role |
| x11 | X11 packages and build dependencies only, skipping the source builds |

## Variables

See [defaults/main.yml](./defaults/main.yml).

## Configuration Files

- `~/.config/bspwm/bspwmrc` - BSPWM configuration
- `~/.config/sxhkd/sxhkdrc` - Keyboard shortcuts
