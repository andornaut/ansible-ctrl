# ansible-role-bspwm

Installs [BSPWM](https://github.com/baskerville/bspwm) and the X11 utilities its session requires, on Ubuntu.

## Usage

Applied by `desktop.yml` when `desktop_environment == "bspwm"`.

```bash
make desktop
make desktop -- --tags bspwm
```

## Tags

| Tag   | Description                                                    |
| ----- | -------------------------------------------------------------- |
| bspwm | Everything in this role                                        |
| x11   | X11 packages and build dependencies, but not the source builds |

## Variables

See [defaults/main.yml](./defaults/main.yml).

## Notes

- BSPWM and the [baskerville](https://github.com/baskerville) tools in `bspwm_projects` are built from source and staged
  over `/usr/local` (binaries, man pages, completions).
- Owns the X11 tools that [niri](../niri/) replaces with Wayland equivalents (`scrot`, `xsecurelock`, `xss-lock`,
  `xbacklight`), plus `dex`, `dbus-x11` and `xorg`. Tools both sessions share live in [desktop](../desktop/).
- Locking uses three programs: the X server blanks and powers off the monitor on `xset` timers, and `xss-lock`
  watches the X screensaver extension and `logind` to start `xsecurelock`. All three timeouts are written into the
  session script by [desktop](../desktop/README.md#idle-locking-and-suspend).
- The X session is `/usr/local/bin/bspwm-session`, which `bspwm.desktop` names. It imports `DISPLAY` and
  `XAUTHORITY` into the user manager, holds `bspwm-session.target` while bspwm runs and stops it after.
  `graphical-session.target` ships `StopWhenUnneeded=yes`, so it stays up only while an active unit requires it, and
  that target (`BindsTo=graphical-session.target`) is the one unit that does, which is why no unit wanted by the
  session may take its place ([desktop](../desktop/README.md#desktop-environments)). A session already logged in when
  the role runs has the target held for it, as a fresh login would.
