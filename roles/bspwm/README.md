# ansible-role-bspwm

Installs [BSPWM](https://github.com/baskerville/bspwm) and the X11 utilities its session requires, on Ubuntu.

## Usage

Applied by `desktop.yml` when `desktop_environment == "bspwm"`.

```bash
make desktop
make desktop -- --tags bspwm
```

## Tags

| Tag | Description |
| --- | --- |
| bspwm | Everything in this role |
| x11 | X11 packages and build dependencies, but not the source builds |

## Variables

See [defaults/main.yml](./defaults/main.yml).

## Notes

- BSPWM and the [baskerville](https://github.com/baskerville) tools in `bspwm_projects` are built from source into
  `/usr/local/bin`.
- This role owns the X11 tools that the [niri](../niri/) role replaces with Wayland equivalents (`scrot`,
  `xsecurelock`, `xss-lock`, `xbacklight`), plus `dex` and `xorg`. Tools both sessions share live in the
  [desktop](../desktop/) role.
- Locking uses three programs: the X server blanks and powers off the monitor on `xset` timers, `xss-lock` watches
  the X screensaver extension and `logind` and starts `xsecurelock`. The
  [desktop](../desktop/README.md#idle-locking-and-suspend) role writes all three timeouts into the session script.
