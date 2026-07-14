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
| x11 | X11 packages and build dependencies, and the removal of the xscreensaver that xsecurelock replaced, but not the source builds |

## Variables

See [defaults/main.yml](./defaults/main.yml).

## Notes

- BSPWM and the [baskerville](https://github.com/baskerville) tools listed in `bspwm_projects` are built from
  source into `/usr/local/bin`.
- This role owns only the X11 tools that have a Wayland replacement in the [niri](../niri/) role: `scrot` (grim
  and slurp), `xsecurelock` and `xss-lock` (hypridle and hyprlock), `xbacklight` (brightnessctl), plus `dex` and
  `xorg`. Tools both sessions share live in the [desktop](../desktop/) role.
- Locking is three programs, not one. The X server blanks the screen and powers the monitor down on its own
  `xset` timers; `xss-lock` watches the X screensaver extension and `logind`, and starts `xsecurelock` on either.
  The [desktop](../desktop/) role writes all three timeouts into the session script that starts `xss-lock`.
- This role used to build [xscreensaver](https://www.jwz.org/xscreensaver/) from source, because Ubuntu ships a
  2023 build. It was replaced because its unlock dialog cannot see ordinary key events: the daemon holds the
  keyboard grab, so the dialog snoops XInput2 **raw** events, which carry no modifier state (it recovers case by
  polling `XQueryPointer`, racing fast typing) and never auto-repeat. `xsecurelock` inverts that: the grabbing
  process reads real `KeyPress` events and pipes the decoded text to a separate auth child.

## Configuration files

| Path | Purpose |
| --- | --- |
| `~/.config/bspwm/bspwmrc` | BSPWM configuration |
| `~/.config/sxhkd/sxhkdrc` | Keyboard shortcuts |
