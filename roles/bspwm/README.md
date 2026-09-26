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

See [defaults/main.yml](./defaults/main.yml). Each `bspwm_projects` entry takes an optional `version`
(a tag, branch or commit), defaulting to `HEAD`.

## Installed files

| Path                                               | Purpose                                                                                                  |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `/usr/local` (binaries, man pages, completions)    | BSPWM and the [baskerville](https://github.com/baskerville) tools in `bspwm_projects`, built from source |
| `/usr/local/bin/bspwm-session`                     | The X session command that `bspwm.desktop` names                                                         |
| `/usr/local/share/xsessions/bspwm.desktop`         | Session entry for the display manager                                                                    |
| `/usr/local/lib/systemd/user/bspwm-session.target` | Held by `bspwm-session` while bspwm runs                                                                 |

## Notes

| Constraint            | Detail                                                                                                                                                                                        |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| X11-only              | This role owns the X11 tools that [niri](../niri/) replaces (`scrot`, `xsecurelock`, `xss-lock`, `xbacklight`), plus `dex`, `dbus-x11` and `xorg`. Shared tools are in [desktop](../desktop/) |
| Locking               | [desktop](../desktop/README.md#idle-locking-and-suspend) sets the timeouts                                                                                                                    |
| Session wrapper       | `bspwm-session` holds `graphical-session.target` while bspwm runs; see [desktop](../desktop/README.md#desktop-environments)                                                                   |
| Locked encrypted home | The run fails before any change while `bspwm_user`'s encrypted home is not mounted. Log in as that user or run `ecryptfs-mount-private`, then re-run                                          |
| Rebuilt on every run  | `bspwm_projects` build from `HEAD` by default                                                                                                                                                 |
