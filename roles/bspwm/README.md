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
  and slurp), `xss-lock` and `i3lock` (hypridle and hyprlock), `xbacklight` (brightnessctl), plus `dex` and
  `xorg`. Tools both sessions share live in the [desktop](../desktop/) role.
- `xss-lock` runs `i3lock` when the X screensaver activates, on `loginctl lock-session`, and before the system
  sleeps. The desktop role programs the timeouts with `xset`. It supersedes `xscreensaver`, `xautolock` and
  `gnome-screensaver`, all of which this role purges.

## Configuration files

| Path | Purpose |
| --- | --- |
| `~/.config/bspwm/bspwmrc` | BSPWM configuration |
| `~/.config/sxhkd/sxhkdrc` | Keyboard shortcuts |
