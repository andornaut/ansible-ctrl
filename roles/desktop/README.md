# ansible-role-desktop

Configures a Linux desktop environment and common applications on Ubuntu.

## Usage

```bash
make desktop
make desktop -- --tags browser
```

## Tags

Tags marked *tiling* are skipped when `desktop_environment` is `gnome`.

| Tag | Description |
| --- | --- |
| [alacritty](https://alacritty.org/) | Terminal emulator |
| browser | [Google Chrome](https://www.google.com/chrome/) and [Firefox](https://www.firefox.com/), then points `xdg-settings` at `desktop_default_browser` |
| [coolercontrol](https://gitlab.com/coolercontrol/coolercontrol) | Fan and pump curve control |
| [dconf](https://wiki.gnome.org/Projects/dconf) | GNOME settings (keyboard layout, input sources) |
| display-manager | [lemurs](https://github.com/coastalwhite/lemurs) or [ly](https://github.com/fairyglade/ly), *tiling* |
| [dunst](https://dunst-project.org/) | Notification daemon, built from source, *tiling* |
| [eww](https://github.com/elkowar/eww) | Widget daemon, *tiling* |
| [file-roller](https://gitlab.gnome.org/GNOME/file-roller) | Default handler for archive MIME types |
| [flameshot](https://flameshot.org/) | Screenshot tool's systemd user unit, tied to eww's tray, *tiling* |
| [flatpak](https://flatpak.org/) | Flatpak runtime and Flathub apps |
| fonts | System fonts |
| gnome | GNOME Shell and gdm3, gnome only |
| [grub](https://www.gnu.org/software/grub/) | Bootloader settings |
| idle | Screen blanking, session locking, monitor power-off, idle suspend, and the backstop under them all |
| [insync](https://www.insynchq.com/) | Google Drive sync client (`desktop_install_insync`) |
| [it87](https://github.com/frankcrawford/it87) | DKMS Super I/O driver for ITE chips on Gigabyte AM5 boards (`desktop_install_it87`) |
| [lact](https://github.com/ilya-zlobintsev/LACT) | AMD GPU control utility |
| [nct6687d](https://github.com/Fred78290/nct6687d) | DKMS Super I/O driver for Nuvoton chips on MSI boards (`desktop_install_nct6687d`) |
| parental-controls | [malcontent](https://gitlab.freedesktop.org/pwithnall/malcontent) filter, web filter, and Chrome policies |
| [pavolume](https://github.com/andornaut/pavolume) | PulseAudio volume controller, *tiling* |
| [rofi](https://github.com/lbonn/rofi) | Application launcher (Wayland fork, built from source), *tiling* |
| theme | GTK themes, the GNOME colour scheme, and the flatpak theme override |
| usb-autosuspend | udev rule pinning autosuspend off for `desktop_usb_no_autosuspend_vendor_ids` |

## Variables

See [defaults/main.yml](./defaults/main.yml). The ones whose behaviour is not obvious from the name:

| Variable | Purpose |
| --- | --- |
| `desktop_environment` | `bspwm`, `niri`, or `gnome`. Selects the window manager `desktop.yml` applies, and which tags run. Required and asserted; no default |
| `desktop_default_browser` | `firefox` or `google-chrome`. The one `xdg-settings` marks as default |
| `desktop_install_*` | Feature flags, all defaulting to `false`. `parental_controls` and `firefox` still run when false, undoing what an earlier run enforced |
| `desktop_screen_*_minutes` | Idle timeouts, in order: blank, lock, monitor power-off |
| `desktop_suspend_inactive_minutes` | Idle suspend. Unset leaves the host's policy alone; 0 disables it |
| `desktop_idle_backstop_minutes` | Minutes of real input idle after which the panel is powered down whatever holds an idle inhibitor; 0 disables it |
| `desktop_xsecurelock_password_prompt` | What the unlock prompt echoes while typing (`asterisks`, `cursor`, `time`, `disco`) |
| `desktop_xsecurelock_auth_background_color` | Tints the password dialog box only, so a tinted box means keystrokes reach the password field. Empty (the default) leaves it black |
| `desktop_parental_controls_web_*` | Web filter for `desktop_user`: filter type, filter lists, custom hostnames, safe search |
| `desktop_zig_mirror` | Mirror to download the Zig toolchain from when building the `ly` display manager |

## Desktop environments

| Rule | Detail |
| --- | --- |
| `gnome` installs GNOME Shell and gdm3, and skips the tiling-only tags | GNOME ships a Wayland-only session, so no Xorg server is installed; legacy X11 apps run under XWayland |
| Tiling hosts get the tags marked *tiling*, plus the X11 tools both tiling sessions use ([tasks/apt_tiling.yml](./tasks/apt_tiling.yml)) | niri runs them as XWayland clients |
| Only tools with a per-protocol replacement belong to [bspwm](../bspwm/) (X11) or [niri](../niri/) (Wayland) | Everything both sessions share lives here |
| `ly` is built with Zig from `desktop_zig_mirror`, a [community mirror](https://ziglang.org/download/community-mirrors.txt) | The ziglang.org origin is slow. The archive is checksummed against the shasum the origin publishes |

## Idle, locking and suspend

The three `desktop_screen_*_minutes` timeouts are one policy with three mechanisms, and only X11 tells blanking
apart from powering the monitor down:

| Environment | Mechanism | Timeouts honoured |
| --- | --- | --- |
| gnome | dconf | blank, lock |
| bspwm | `xss-lock` and the X server | blank, lock, power-off |
| niri | `hypridle` | lock, power-off |

Under bspwm the timeouts are set once per session by `/usr/local/bin/xsecurelock-session`, run by the autostart
entry at login. Nothing reloads them, so a change takes effect at the next login.

| Constraint | Detail |
| --- | --- |
| A blanked screen is not a locked one | X11 blanking takes no keyboard grab, so during the blank-to-lock grace a keystroke both wakes the screen and lands in the focused window. Setting `desktop_screen_lock_minutes` equal to `desktop_screen_blank_minutes` closes that window, at the cost of the no-password return period |
| Two `XSECURELOCK_*` settings are security-relevant ([templates/xsecurelock-session.j2](./templates/xsecurelock-session.j2)) | `FORCE_GRAB=1` forces the grab, so a fullscreen game or open menu cannot leave the session unlocked silently. `DISCARD_FIRST_KEYPRESS=1` swallows the key that dismisses the blank screen, so nobody types a password at a black screen. Authentication needs nothing setuid (`common-auth` PAM service, `unix_chkpwd`) |

### Suspend

`desktop_suspend_inactive_minutes` is a separate policy. `logind` cannot detect idleness itself, so GNOME uses
`gnome-settings-daemon`, niri a `hypridle` listener, and bspwm has `xss-lock` set the session's idle hint when the
X screensaver activates.

| Constraint | Detail |
| --- | --- |
| The bspwm `logind` drop-in gets `desktop_suspend_inactive_minutes` *minus* `desktop_screen_blank_minutes` | `IdleActionSec` counts from the idle hint, set at blank time. The variable therefore means "suspend this long after the last input" on every desktop, and must be 0 or greater than the blank timeout (asserted by the `idle` tag) |
| Under bspwm the policy is host-wide | An idle `ssh` login also delays suspend. A host that moves off bspwm has the drop-in removed |
| On niri the value renders into `.config/hypr/hypridle.conf`, a shared dotfiles symlink | Two niri hosts with different values fight over that managed block. Give niri hosts the same value, or move to a role-owned per-host file as the bspwm side has |

### Idle backstop

Every mechanism above honours an idle inhibitor, any application may take one through `org.freedesktop.ScreenSaver`
(GNOME), `XScreenSaverSuspend` (X11) or `idle-inhibit-unstable-v1` (Wayland), and none of the three caps how long
one may be held. A game usually holds one for its whole run: GameMode does by default, and SDL and GLFW both do for
any window they open. That leaves a static image lit for as long as the game is up, which is what
`desktop_idle_backstop_minutes` exists to stop.

`desktop-idle-backstop.service`, a user unit wanted by `graphical-session.target`, polls an idle counter no
inhibitor can freeze and powers the panel down from outside the compositor:

| Environment | Reads | Powers the panel down with |
| --- | --- | --- |
| gnome | `org.gnome.Mutter.IdleMonitor.GetIdletime` | `ddcutil setvcp d6 04`, then `d6 01` on the next input |
| bspwm | `xprintidle`, so `XScreenSaverQueryInfo` | `xset dpms force off`, which the X server undoes itself |
| niri | `desktop-idle-input`, reading the input devices | `niri msg action power-off-monitors`, which [templates/hypridle.conf.j2](./templates/hypridle.conf.j2) also uses |

| Constraint | Detail |
| --- | --- |
| niri needs a reader of its own, `desktop-idle-input.service` | `hypridle` learns of idleness through `ext-idle-notify-v1`, which the compositor gates on idle inhibitors, so it is the one mechanism the backstop must not share. The reader watches the input devices instead and publishes the time of the last one to `/run/desktop-idle-input/stamp`, which is compositor-independent by construction. Installed only where the mechanism is `niri`, and removed from a host that leaves it |
| The reader is a root system service, not part of the session | Reading the devices as the session's own account would mean putting it in the `input` group, which lets anything running as that account read every keystroke. Under Wayland, where a client otherwise cannot, that gives away more than the backstop is worth. It publishes only a time, never what was pressed |
| The stamp carries a heartbeat beside the idle time | A reader that dies leaves the idle time frozen, and a frozen number reads as a session going idle, which would blank a panel someone is sitting in front of. The backstop refuses a stamp whose heartbeat is over `desktop_idle_input_stale_seconds` old and exits for a restart instead |
| `EV_ABS` events are not counted as input | A gamepad with a drifting analog stick emits them forever, and a controller left on a couch beside a running game is the case the backstop exists for. Touchpads, touchscreens and tablets all report a `BTN_*` key event on contact, so they still count |
| GNOME reaches the monitor over DDC/CI rather than DPMS | GNOME is Wayland-only, so nothing outside mutter can reach an output. `d6 04` is DPM off, which the panel keeps answering the bus from, so `d6 01` restores it without its power button. A monitor implementing neither cannot be backstopped this way; `ddcutil capabilities` says which values `d6` takes |
| The threshold must clear `desktop_screen_blank_minutes`, and is asserted by the `idle` tag | Below the blank timeout it pre-empts the session's own blanking rather than flooring it |
| `desktop_suspend_inactive_minutes` does not bound it, even where it is shorter | An idle inhibitor defers idle suspend as surely as it defers blanking, so a backstop above the suspend timeout still fires in the one case suspend cannot, and stays out of the way when nothing inhibits and the host suspends first |
| It needs no root and no group of its own | `ddcutil`'s udev rule tags the I2C device `uaccess`, so the bus is granted to whoever is logged in locally and revoked with the session. `ddcutil` also ships the `modules-load.d` entry for `i2c-dev` |
| The panel comes back up when the service stops | A monitor left in DDC standby outlives the session and greets the next login looking dead |
| It exits after three failed idle reads rather than logging them forever | Started outside a graphical session it has no display and no session bus, and `systemctl --user import-environment` reaches the user manager rather than a running service, so only the restart picks the session up. A restart loop is also the visible sign that it is backstopping nothing |
| A failed wake is retried, a failed power-off is not | A panel left dark in front of someone typing is the worse failure. The power-off case is usually a panel that has already gone dark on its own and stopped answering, and `ddcutil` retries the write itself |
| Polling is 30s while the panel is lit and 2s while it is dark | Nothing waits on the first; the second is the wake latency felt at the keyboard |

### Writing dotfiles that may be symlinks

A path that may be a dotfiles-repo symlink, such as `.config/hypr/hypridle.conf`, rules out `template`/`copy`:
their no-op path re-runs the `file` module against the resolved target, and `file` expands `$HOME` in that path,
corrupting a repo tree under a `$HOME`-named directory. `blockinfile` writes through the link instead, and
[tasks/idle_check_dotfile.yml](./tasks/idle_check_dotfile.yml) classifies the path first, failing on a dangling
link rather than orphaning it.

## Parental controls

Web filtering is enforced in the name service switch, not the browser. `nss-malcontent` sinkholes a blocked
hostname for users with a compiled filter list under `/var/lib/malcontent-webd/filter-lists/` and defers for
everyone else, so the `/etc/nsswitch.conf` edit is system-wide while the policy stays per-user.

| Constraint | Detail |
| --- | --- |
| Matching is exact: a cdb keyed on whole hostnames, no wildcards or subdomains | Filter lists must be plain newline-separated bare hostnames over HTTPS. One malformed line aborts the update, leaving the previous list |
| The `use-application-dns.net` canary is blocked for every user | It turns DoH off in every Firefox, which otherwise resolves past the module |
| Chrome merges every file in `/etc/opt/chrome/policies/managed/`, later name winning | A `family.json.bak` outranks the original, so the role owns the directory and sweeps anything it did not deploy |
| The role asserts the chosen list type has entries | An empty allow list sinkholes everything; an empty block list filters nothing while reporting filtering is on |
| Both flatpak installation permissions are passed explicitly | Setting any OARS ceiling also disallows installation from the system repository, which the role restores when it clears the filter |
| Clearing `desktop_install_parental_controls` lifts the controls rather than ceasing to reassert them | The tag runs on every desktop host and, with the flag false, clears both `malcontent` filters and removes the Chrome policy. Remove the host's `desktop_parental_controls_*` block too: the role asserts no setting is left describing a policy nothing enforces |
