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
  Wayland-only session, so no Xorg server is installed; legacy X11 apps run under XWayland.
- Tiling hosts additionally get a display manager, dunst, eww, rofi, pavolume, and the X11 tools both tiling
  sessions use, since niri runs them as XWayland clients ([apt_tiling.yml](./tasks/apt_tiling.yml)).
- Only tools with a true per-protocol replacement belong to the [bspwm](../bspwm/) role (X11) and the
  [niri](../niri/) role (Wayland). Everything both sessions share lives here.
- `ly` is built with Zig, downloaded from `desktop_zig_mirror` (a
  [community mirror](https://ziglang.org/download/community-mirrors.txt)) rather than the slow ziglang.org origin;
  the archive is checksummed against the shasum the origin publishes.

## Idle, locking and suspend

The three idle timeouts (`desktop_screen_*_minutes`) are one policy with three mechanisms: GNOME reads dconf, bspwm
delegates to `xss-lock` and the X server, niri to `hypridle`. Only X11 tells blanking apart from powering the
monitor down, so bspwm honours all three timeouts, niri ignores the blank timeout, and GNOME ignores the power-off
timeout.

Under bspwm the timeouts are set once per session by `/usr/local/bin/xsecurelock-session`, run by the autostart
entry at login; nothing reloads them, so a change takes effect at the next login. **A blanked screen is not a
locked one:** X11 blanking takes no keyboard grab, so during the blank-to-lock grace a keystroke both wakes the
screen and lands in the focused window. Set `desktop_screen_lock_minutes` equal to `desktop_screen_blank_minutes`
to close that window, at the cost of the no-password return period.

Two security-relevant `XSECURELOCK_*` settings (see [xsecurelock-session.j2](./templates/xsecurelock-session.j2)):
`XSECURELOCK_FORCE_GRAB=1` forces the grab so a fullscreen game or open menu cannot leave the session unlocked
silently, and `XSECURELOCK_DISCARD_FIRST_KEYPRESS=1` swallows the key that dismisses the blank screen so nobody
types a password at a black screen. Authentication needs nothing setuid (`common-auth` PAM service, `unix_chkpwd`).

### Suspend

Idle suspend is a separate policy (`desktop_suspend_inactive_minutes`). `logind` cannot detect idleness itself:
GNOME uses `gnome-settings-daemon`, niri a `hypridle` listener, and bspwm has `xss-lock` set the session's idle
hint when the X screensaver activates. `IdleActionSec` counts from that hint (set at blank time), so the bspwm
`logind` drop-in gets `desktop_suspend_inactive_minutes` *minus* `desktop_screen_blank_minutes`, keeping the
variable meaning "suspend this long after the last input" on every desktop. It must therefore be 0 or greater than
the blank timeout (the `idle` tag asserts it). Under bspwm the policy is host-wide, so an idle `ssh` login also
delays suspend; a host that moves off bspwm has the drop-in removed.

**Known issue:** `desktop_suspend_inactive_minutes` renders into `.config/hypr/hypridle.conf`, a shared dotfiles
symlink, so two niri hosts with different values would fight over that managed block. Latent while every host uses
the same values; the fix is a role-owned per-host file, as the bspwm side already has.

### Writing dotfiles that may be symlinks

`.config/hypr/hypridle.conf` may be a dotfiles-repo symlink, which rules out `template`/`copy`: their no-op path
re-runs the `file` module against the resolved target, and `file` expands `$HOME` in that path, corrupting a repo
tree under a `$HOME`-named directory. `blockinfile` writes through the link instead.
[idle_check_dotfile.yml](./tasks/idle_check_dotfile.yml) classifies the path first and fails on a dangling link
rather than orphaning it.

## Parental controls

Web filtering is enforced in the name service switch, not the browser. `nss-malcontent` sinkholes a blocked
hostname for users with a compiled filter list under `/var/lib/malcontent-webd/filter-lists/` and defers for
everyone else, so the `/etc/nsswitch.conf` edit is system-wide while the policy stays per-user.

- Matching is exact (a cdb keyed on whole hostnames, no wildcards or subdomains). Filter lists must be plain
  newline-separated bare hostnames over HTTPS; one malformed line aborts the update, leaving the previous list.
- The `use-application-dns.net` canary is blocked for every user, turning DoH off in every Firefox (DoH would
  otherwise resolve past the module).
- Chrome merges every file in `/etc/opt/chrome/policies/managed/`, later name winning, so a `family.json.bak` is a
  second policy that outranks the original. The role owns the directory and sweeps anything it did not deploy.
- An empty allow list sinkholes everything; an empty block list filters nothing while reporting filtering is on.
  The role asserts the chosen list type has entries.
- Setting any OARS ceiling also disallows flatpak installation from the system repository, so the role passes both
  installation permissions explicitly and restores the system repository when it clears the filter.

**Turning `desktop_install_parental_controls` off lifts the controls** rather than ceasing to reassert them: the
tag runs on every desktop host and, with the flag false, clears both `malcontent` filters and removes the Chrome
policy. Tearing down means removing the host's `desktop_parental_controls_*` block, not just the flag; the role
asserts no setting is left describing a policy nothing enforces.
