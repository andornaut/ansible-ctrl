# ansible-role-bspwm

Installs [BSPWM](https://github.com/baskerville/bspwm) and the X11 utilities its session requires, on Ubuntu.

## Usage

Applied by `desktop.yml` when `desktop_environment == "bspwm"`.

```bash
make desktop
make desktop -- --tags bspwm
```

## Tags

| Tag         | Description                                                                                                                                                     |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| app-entries | Desktop entry overrides for the applications this role installs, from `bspwm_app_entry_overrides`; same mechanism as the [desktop](../desktop/README.md) role's |
| bspwm       | Everything in this role                                                                                                                                         |
| x11         | X11 packages and build dependencies, but not the source builds                                                                                                  |

## Variables

See [defaults/main.yml](./defaults/main.yml).

## Installed files

| Path                                               | Purpose                                                                                                  |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `/usr/local` (binaries, man pages, completions)    | BSPWM and the [baskerville](https://github.com/baskerville) tools in `bspwm_projects`, built from source |
| `/usr/local/bin/bspwm-session`                     | The X session command that `bspwm.desktop` names                                                         |
| `/usr/local/share/xsessions/bspwm.desktop`         | Session entry for the display manager                                                                    |
| `/usr/local/lib/systemd/user/bspwm-session.target` | Held by `bspwm-session` while bspwm runs                                                                 |

## Notes

| Constraint                | Detail                                                                                                                                                                                                                                                                                           |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| User manager reload       | Conditional on `bspwm_user`'s manager socket, which exists only while that account is logged in. On a host where `bspwm_user` is not logged in the reload is skipped; a manager started later reads the unit directory at startup                                                                |
| X11-only                  | This role owns the X11 tools that [niri](../niri/) replaces with Wayland equivalents (`scrot`, `xsecurelock`, `xss-lock`, `xbacklight`), plus `dex`, `dbus-x11` and `xorg`. Tools both sessions share are in [desktop](../desktop/)                                                              |
| Locking                   | The X server blanks and powers off the monitor on `xset` timers, and `xss-lock` watches the X screensaver extension and `logind` to start `xsecurelock`. [desktop](../desktop/README.md#idle-locking-and-suspend) writes all three timeouts into the session script                              |
| Session wrapper           | `bspwm-session` imports `DISPLAY` and `XAUTHORITY` into the user manager and holds `bspwm-session.target` (`BindsTo=graphical-session.target`) while bspwm runs, then stops it. This is the unit that holds `graphical-session.target`; see [desktop](../desktop/README.md#desktop-environments) |
| Session already logged in | The role holds the target for a session that was already running when it applied, as a fresh login would                                                                                                                                                                                         |
