# ansible-role-bspwm

Installs [BSPWM](https://github.com/baskerville/bspwm) and the X11 utilities its session requires, on Ubuntu.

## Usage

Applied by `desktop.yml` when `desktop_environment == "bspwm"`.

```bash
make desktop

ansible-playbook --ask-become-pass desktop.yml --tags bspwm
```

## Tags

| Tag | Description |
| --- | --- |
| bspwm | Everything in this role |
| x11 | X11 packages and build dependencies only, skipping the source builds |

## Variables

See [defaults/main.yml](./defaults/main.yml).

## Notes

- BSPWM and the [baskerville](https://github.com/baskerville) tools listed in `bspwm_projects` are built from
  source into `/usr/local/bin`.
- This role owns only the X11 tools that have a Wayland replacement in the [niri](../niri/) role: `scrot` (grim
  and slurp), `xautolock` (hypridle), `xbacklight` (brightnessctl), plus `dex` and `xorg`. Tools both sessions
  share live in the [desktop](../desktop/) role.

## Configuration files

| Path | Purpose |
| --- | --- |
| `~/.config/bspwm/bspwmrc` | BSPWM configuration |
| `~/.config/sxhkd/sxhkdrc` | Keyboard shortcuts |
