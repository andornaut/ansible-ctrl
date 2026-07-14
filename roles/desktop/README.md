# ansible-role-desktop

Configures a Linux desktop environment and common applications on Ubuntu.

## Usage

```bash
make desktop
make desktop -- --tags browser
```

## Tags

| Tag | Description |
| --- | --- |
| [alacritty](https://alacritty.org/) | Terminal emulator |
| browser | [Google Chrome](https://www.google.com/chrome/) and [Firefox](https://www.mozilla.org/firefox/), then points `xdg-settings` at `desktop_default_browser` |
| [coolercontrol](https://gitlab.com/coolercontrol/coolercontrol) | Fan and pump curve control |
| [dconf](https://wiki.gnome.org/Projects/dconf) | GNOME settings (keyboard layout, input sources) |
| display-manager | Display manager ([lemurs](https://github.com/coastalwhite/lemurs) or [ly](https://github.com/fairyglade/ly)), tiling only |
| [dunst](https://dunst-project.org/) | Notification daemon (built from source), tiling only |
| [eww](https://github.com/elkowar/eww) | Widget daemon, tiling only |
| [file-roller](https://gitlab.gnome.org/GNOME/file-roller) | Default handler for archive MIME types |
| [flatpak](https://flatpak.org/) | Flatpak runtime and Flathub apps |
| fonts | System fonts |
| gnome | GNOME Shell and gdm3, gnome only |
| [grub](https://www.gnu.org/software/grub/) | Bootloader settings |
| idle | Screen blanking, session locking, monitor power-off, and idle suspend |
| [insync](https://www.insynchq.com/) | Google Drive sync client (`desktop_install_insync`) |
| [it87](https://github.com/frankcrawford/it87) | DKMS Super I/O driver for ITE chips on Gigabyte AM5 boards (`desktop_install_it87`) |
| [lact](https://github.com/ilya-zlobintsev/LACT) | AMD GPU control utility |
| [nct6687d](https://github.com/Fred78290/nct6687d) | DKMS Super I/O driver for Nuvoton chips on MSI boards (`desktop_install_nct6687d`) |
| parental-controls | [malcontent](https://gitlab.freedesktop.org/pwithnall/malcontent) filter, web filter, and Chrome policies |
| [pavolume](https://github.com/andornaut/pavolume) | PulseAudio volume controller, tiling only |
| [rofi](https://github.com/lbonn/rofi) | Application launcher (Wayland fork, built from source), tiling only |
| theme | GTK themes, the GNOME colour scheme, and the flatpak theme override |

## Variables

See [defaults/main.yml](./defaults/main.yml).

| Variable | Purpose |
| --- | --- |
| `desktop_environment` | `bspwm`, `niri`, or `gnome`. Selects the window manager `desktop.yml` applies, and which tags run |
| `desktop_default_browser` | `firefox` or `google-chrome`. The one `xdg-settings` marks as default |
| `desktop_install_*` | Feature flags, all defaulting to `false`. `parental_controls` and `firefox` still run when false, to undo what an earlier run enforced |
| `desktop_screen_*_minutes` | Idle timeouts. The screen blanks, then the session locks, then the monitor powers off |
| `desktop_suspend_inactive_minutes` | Idle suspend. Unset leaves the host's policy alone; 0 disables it |
| `desktop_xsecurelock_password_prompt` | What the unlock prompt echoes while typing (`asterisks`, `cursor`, `time`, `disco`) |
| `desktop_parental_controls_web_*` | Web filter for `desktop_user`: filter type, filter lists, custom hostnames, safe search |
| `desktop_zig_mirror` | Mirror to download the Zig toolchain from when building the `ly` display manager |

## Desktop environments

- `desktop_environment: gnome` installs GNOME Shell and gdm3 and skips the tiling-only tags. GNOME ships a
  Wayland-only session, so no Xorg server is installed; legacy X11 apps run under the XWayland it pulls in.
- Tiling hosts additionally get a display manager, dunst, eww, rofi, pavolume, and the X11 tools both tiling
  sessions use, since niri runs them as XWayland clients ([apt_tiling.yml](./tasks/apt_tiling.yml)).
- Only tools with a true per-protocol replacement belong to the [bspwm](../bspwm/) role (X11) and the
  [niri](../niri/) role (Wayland). Everything both sessions share lives here.
- `ly` is built with Zig, downloaded from `desktop_zig_mirror` rather than ziglang.org, whose donated bandwidth
  makes the origin download take about 20 minutes. Set it to a host from
  [community-mirrors.txt](https://ziglang.org/download/community-mirrors.txt); the archive is checksummed against
  the shasum the origin publishes.

## Idle, locking and suspend

The three idle timeouts are one policy with three mechanisms. GNOME reads dconf, bspwm delegates to `xss-lock` and
the X server, niri to `hypridle`. Only X11 tells blanking apart from powering the monitor down, so bspwm honours
all three timeouts, niri ignores the blank timeout, and GNOME ignores the power-off timeout.

Under bspwm the timeouts are set once per session by `/usr/local/bin/xsecurelock-session`, which the autostart
entry runs at login. Nothing reloads them, so a timeout change takes effect at the next login. `xset s` blanks the
screen, `xss-lock` starts `xsecurelock` one cycle later (the blank-to-lock grace, like GNOME's `lock-delay`), and
`xset dpms` powers the monitor down.

**A blanked screen is not a locked one.** X11 blanking takes no keyboard grab, so during the grace period a
keystroke both wakes the screen and lands in whatever window has focus. Setting `desktop_screen_lock_minutes` equal
to `desktop_screen_blank_minutes` closes that window, at the cost of the no-password return period.

Two `XSECURELOCK_*` settings are security-relevant rather than preferences:

- **`XSECURELOCK_FORCE_GRAB=1`.** `xsecurelock` cannot lock while another window holds the keyboard or pointer grab
  (a fullscreen game, an open context menu). Without this it exits and the session stays unlocked silently; forcing
  the grab unmaps the offending windows, takes the grab, and maps them back. The price is that a fullscreen window
  that held the grab is left unresponsive afterwards (alt-tab recovers it). Hosts in this group run Steam and
  RetroArch fullscreen.
- **`XSECURELOCK_DISCARD_FIRST_KEYPRESS=1`.** The key that dismisses the blank screen is swallowed rather than
  typed into the password field, so nobody learns to type a password at a black screen.

Authentication needs nothing setuid: `xsecurelock` uses the PAM service in the Ubuntu package (`common-auth`), and
`pam_unix` reaches `/etc/shadow` through the `unix_chkpwd` helper.

### Suspend

Idle suspend is a separate policy, driven by `desktop_suspend_inactive_minutes`. `logind` cannot detect idleness
itself: GNOME uses `gnome-settings-daemon`, niri a `hypridle` listener, and bspwm has `xss-lock` set the session's
idle hint as the X screensaver activates. Because `IdleActionSec` counts from that hint (set when the screen
blanks), the bspwm `logind` drop-in gets `desktop_suspend_inactive_minutes` *minus* `desktop_screen_blank_minutes`,
so the variable keeps meaning "suspend this long after the last input" on every desktop. The value must therefore
be 0 or strictly greater than the blank timeout, which the `idle` tag asserts: equal timeouts render
`IdleActionSec=0`, which `logind` reads as *no* idle action.

Under bspwm the policy is host-wide, not per-session, so an idle `ssh` login also has to be idle before the host
suspends. A host that moves off bspwm has the drop-in removed with its session script, so it stops suspending to a
policy nothing manages.

**Known issue:** `desktop_suspend_inactive_minutes` is rendered into `.config/hypr/hypridle.conf`, a symlink into
the shared dotfiles repository. Two niri hosts with different values would fight over that managed block in git. It
is latent only because every host currently uses the same values; the fix is to render per-host policy into a file
the role owns outright, as the bspwm side already does.

### Writing dotfiles that may be symlinks

`.config/hypr/hypridle.conf` may be a symlink into a dotfiles repository, which rules out `template` and `copy`: on
a no-op run their action plugin re-runs the `file` module against the resolved link target, and `file` expands
environment variables in that path, corrupting it for a repository whose tree lives under a directory named
`$HOME`. `blockinfile` resolves the link and writes through it, so the config is wrapped in an
`ANSIBLE MANAGED BLOCK` instead. A *dangling* link is a separate problem, so
[idle_check_dotfile.yml](./tasks/idle_check_dotfile.yml) classifies the path first and fails with a clear message
rather than orphaning the link.

## Parental controls

Web filtering is enforced in the name service switch, not the browser. `nss-malcontent` sinkholes a blocked
hostname for users with a compiled filter list under `/var/lib/malcontent-webd/filter-lists/` and defers for
everyone else, so the `/etc/nsswitch.conf` edit is system-wide while the policy stays per-user.

- Matching is exact: the compiled list is a cdb keyed on whole hostnames, no wildcards or subdomain matching.
  Filter lists must be plain newline-separated bare hostnames served over HTTPS, and a single malformed line aborts
  the update, leaving the previous list in place.
- The `use-application-dns.net` canary is blocked for *every* user on a host with the module installed, which turns
  DNS-over-HTTPS off in every user's Firefox: DoH would otherwise resolve past the module entirely.
- Chrome merges *every* file in `/etc/opt/chrome/policies/managed/`, later file winning, so a `family.json.bak`
  left beside `family.json` is a second policy that outranks the original. The role owns the directory and sweeps
  anything it did not deploy.
- An allow list with no entries sinkholes everything, and a block list with no entries filters nothing while
  reporting that filtering is on. The role asserts that whichever list type is chosen has entries.
- Setting any OARS ceiling also disallows flatpak installation from the *system* repository (malcontent's own
  default for a filtered account), so the role passes both installation permissions explicitly and restores the
  system repository when it clears the filter.

**Turning `desktop_install_parental_controls` off lifts the controls** rather than merely ceasing to reassert them:
the tag runs on every desktop host, and with the flag false it clears both `malcontent` filters for `desktop_user`
and removes the Chrome policy file. Leaving an enforced filter behind would be worse than never setting one, since
nothing would say why an application is hidden or a domain fails to resolve. Tearing down means removing the host's
`desktop_parental_controls_*` block, not just the flag; the role asserts no setting is left describing a policy
that nothing enforces.
