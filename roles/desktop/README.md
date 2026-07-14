# ansible-role-desktop

Configures a Linux desktop environment and common applications on Ubuntu.

## Usage

```bash
make desktop

ansible-playbook --ask-become-pass desktop.yml --tags browser
```

## Tags

| Tag | Description |
| --- | --- |
| [alacritty](https://alacritty.org/) | Terminal emulator |
| browser | [Google Chrome](https://www.google.com/chrome/) and [Firefox](https://www.mozilla.org/firefox/) (Flathub flatpak, or the Mozilla apt repo when `desktop_install_firefox_apt`; omitted and any existing install removed when `desktop_install_firefox: false`), then points `xdg-settings` at `desktop_default_browser` |
| [coolercontrol](https://gitlab.com/coolercontrol/coolercontrol) | Fan and pump curve control (Cloudsmith apt repo) |
| [dconf](https://wiki.gnome.org/Projects/dconf) | GNOME settings (keyboard layout, input sources) |
| display-manager | Display manager ([lemurs](https://github.com/coastalwhite/lemurs) or [ly](https://github.com/fairyglade/ly)), tiling only |
| [dunst](https://dunst-project.org/) | Notification daemon (built from source), tiling only |
| [eww](https://github.com/elkowar/eww) | Widget daemon (built with Cargo), tiling only |
| [file-roller](https://gitlab.gnome.org/GNOME/file-roller) | Default handler for archive MIME types |
| [flatpak](https://flatpak.org/) | Flatpak runtime and Flathub apps |
| fonts | System fonts (Hack, DejaVu, Source Code Pro, etc.) |
| gnome | GNOME Shell and gdm3 (`ubuntu-desktop-minimal`), gnome only |
| [grub](https://www.gnu.org/software/grub/) | Bootloader settings |
| idle | Screen blanking, session locking and monitor power-off (dconf, [xsecurelock](https://github.com/google/xsecurelock) via [xss-lock](https://github.com/xdbob/xss-lock), [hypridle](https://github.com/hyprwm/hypridle)) |
| [insync](https://www.insynchq.com/) | Google Drive sync client (`desktop_install_insync`) |
| [it87](https://github.com/frankcrawford/it87) | DKMS Super I/O driver for ITE chips on Gigabyte AM5 boards (`desktop_install_it87`) |
| [lact](https://github.com/ilya-zlobintsev/LACT) | AMD GPU control utility |
| [nct6687d](https://github.com/Fred78290/nct6687d) | DKMS Super I/O driver for Nuvoton chips on MSI boards (`desktop_install_nct6687d`) |
| parental-controls | [malcontent](https://gitlab.freedesktop.org/pwithnall/malcontent) OARS filter, web filter and Chrome SafeSearch policies (`desktop_install_parental_controls`) |
| [pavolume](https://github.com/andornaut/pavolume) | PulseAudio volume controller, tiling only |
| [rofi](https://github.com/lbonn/rofi) | Application launcher (Wayland fork, built from source), tiling only |

## Variables

See [defaults/main.yml](./defaults/main.yml).

| Variable | Purpose |
| --- | --- |
| `desktop_environment` | `bspwm`, `niri`, or `gnome`. Selects the window manager `desktop.yml` applies, and which tags run |
| `desktop_default_browser` | `firefox` or `google-chrome`. The handler `xdg-settings` marks as default |
| `desktop_install_*` | Feature flags, all defaulting to `false`. A tag naming one runs nothing unless the flag is set |
| `desktop_screen_*_minutes` | Idle timeouts. The screen blanks, then the session locks, then the monitor powers off |
| `desktop_parental_controls_web_*` | Web filter for `desktop_user`: filter type, `{id: HTTPS URI}` filter lists, custom hostnames, safe search |
| `desktop_xsecurelock_password_prompt` | What the unlock prompt echoes while typing (`asterisks`, `cursor`, `time`, `disco`) |
| `desktop_xsecurelock_background_color`, `_foreground_color`, `_font` | Appearance of the unlock prompt and of the locked-screen indicator |
| `desktop_xsecurelock_show_locked_indicator` | Whether a locked screen says "Locked" rather than being black like a blanked one |
| `desktop_suspend_inactive_minutes` | Idle suspend, in minutes. Unset (default) leaves the host's policy alone. **Not supported under bspwm**: setting it there fails the play |
| `desktop_zig_mirror` | Mirror to download the Zig toolchain from when building the `ly` display manager |

[vars/main.yml](./vars/main.yml) holds values derived from those defaults (the target user's home directory and
UID, the Zig platform key, the apt packages flatpak replaces, and the `.desktop` id of the default browser).
Role vars outrank `host_vars`, so overriding them there has no effect: override the default they derive from.

## Notes

- `desktop_environment: gnome` installs GNOME Shell and gdm3 and skips the WM-specific tags. GNOME 49+ ships a
  Wayland-only session, so no Xorg server is installed; legacy X11 apps run under the XWayland that GNOME pulls in.
- Tiling hosts additionally get a display manager, dunst, eww, rofi, and pavolume; the session utilities a window
  manager does not provide for itself (blueman, lxappearance, network-manager-gnome, policykit-1-gnome); and the
  X11 tools both tiling sessions use (feh, suckless-tools, wmctrl, xclip, xinput, xsel), since niri runs them as
  XWayland clients.
- Only tools with a true per-protocol replacement belong to the [bspwm](../bspwm/) role (X11) and the
  [niri](../niri/) role (Wayland). Everything both sessions share lives here.
- The Super I/O drivers expose the pwm/fan hwmon that CoolerControl manages. Enable the one matching the board's chip.
- The idle timeouts are one policy with three mechanisms. GNOME reads dconf, bspwm delegates to `xss-lock` and the X
  server, and niri to `hypridle`. Only X11 tells blanking apart from powering the monitor down, so bspwm honours all
  three timeouts, niri ignores the blank timeout, and GNOME ignores the power-off timeout.
- Under bspwm the three timeouts are two clocks, both set by `/usr/local/bin/xsecurelock-session`, which the autostart
  entry runs once per session. `xset s <blank> <grace>` blanks the screen after the blank timeout, and `xss-lock`
  starts `xsecurelock` one *cycle* later, so the cycle is the blank-to-lock grace period, exactly like GNOME's
  `lock-delay`. `xset dpms` powers the monitor down. A cycle of zero disables cycling rather than locking
  immediately, so the grace is floored at a second; `XSECURELOCK_BLANK_TIMEOUT` carries the rest of the power-off
  timeout, because once `xsecurelock` is up it blanks on a clock of its own that would otherwise fire ten minutes
  after locking whatever the policy says.
- **A blanked screen is not a locked one.** `xscreensaver` grabbed the keyboard as soon as it blanked; the X server's
  blanking does not, so during the grace period a keystroke both wakes the screen and lands in whatever window has
  focus. Type a password at a black screen too early and it goes into the focused application. This is why
  `desktop_xsecurelock_show_locked_indicator` exists: a locked screen says "Locked" and a merely blanked one shows
  nothing. Setting `desktop_screen_lock_minutes` equal to `desktop_screen_blank_minutes` removes the window entirely.
- The indicator is an `xsecurelock` **saver module**: any executable that draws into the window named by
  `$XSCREENSAVER_WINDOW`. It is an `xterm` because `-into` reparents it into a window it did not create and nothing
  else installed can; it is not a usable terminal, since the locker holds the keyboard and pointer. The unlock prompt
  itself only appears on a keystroke, in `xsecurelock` as in `xscreensaver`, so it cannot serve as the indicator.
- `xsecurelock` authenticates through PAM under the service name compiled into the Ubuntu package, which is
  `common-auth`, and it ships no PAM file of its own. Nothing is setuid: `pam_unix` reaches `/etc/shadow` through the
  `unix_chkpwd` helper. The `idle` tag asserts that the service file exists, because without it the screen would lock
  and never unlock.
- The unlock prompt is configured entirely through `XSECURELOCK_*` environment variables, which the session script
  exports before it execs `xss-lock`. There are no X resources and no dotfiles involved, so changes take effect at the
  next login.
- Idle **suspend** is a separate policy from idle locking, driven by `desktop_suspend_inactive_minutes`. `logind`
  cannot detect idleness itself: something must call `SetIdleHint`. GNOME uses `gnome-settings-daemon`
  (`sleep-inactive-{ac,battery}-{type,timeout}`); niri uses a `hypridle` listener that runs `systemctl suspend`
  itself. **bspwm has nothing**: `xss-lock` answers `logind`'s `Lock` signal, which is what the session's
  `loginctl lock-session` keybinding sends, but it never calls `SetIdleHint`, so `logind`'s `IdleAction` could never
  fire. Setting the variable on a bspwm host fails the play rather than writing a drop-in that does nothing.
- **Known issue**: `desktop_suspend_inactive_minutes` is rendered into `.config/hypr/hypridle.conf`, a symlink into
  the shared dotfiles repository. Two niri hosts with different values would rewrite that managed block on every
  converge and fight over it in git. It is latent only because every host currently uses the same values. The fix is
  the one the bspwm side already took: render per-host policy into a file the role owns outright
  (`/usr/local/bin/xsecurelock-session`) and leave the dotfiles copy free of host-specific values.
- The session files the `idle` tag writes (`.config/autostart/xss-lock.desktop`, `.config/hypr/hypridle.conf`) may be
  symlinks into a dotfiles repository, which rules out `template` and `copy`: on a no-op run their action plugin
  re-runs the `file` module against the resolved link target, and `file` expands environment variables in that path,
  corrupting it for a repository whose tree lives under a directory named `$HOME`. `blockinfile`, `lineinfile` and
  `replace` resolve the link themselves and write through it, so those files are wrapped in an `ANSIBLE MANAGED
  BLOCK` rather than templated. A *dangling* link is a separate problem, and `stat` reports it as existing unless it
  too follows, so `idle_check_dotfile.yml` classifies each path first and fails with a clear message rather than
  orphaning the link. The session script and the saver are the role's own files under `/usr/local`, so they are
  templated normally.
- Nothing reloads the idle configuration under bspwm: the session script sets the X timeouts and execs `xss-lock`
  once, at login, so a timeout change takes effect at the next one.
- Web filtering is enforced in the name service switch, not in the browser. `nss-malcontent` sinkholes a blocked
  hostname for users that have a compiled filter list under `/var/lib/malcontent-webd/filter-lists/` and defers for
  everyone else, so the `/etc/nsswitch.conf` edit is system-wide while the policy stays per-user. Matching is exact:
  the compiled list is a cdb keyed on whole hostnames, with no wildcards and no subdomain matching. Filter lists must
  be plain newline-separated bare hostnames served over HTTPS, and a single malformed line aborts the update, leaving
  the previous list in place and a message in `/var/lib/malcontent-webd/update-error`.
- The `use-application-dns.net` canary is blocked for *every* user on a host with the module installed, because
  `nss-malcontent` checks it before opening the per-user list. That turns DNS-over-HTTPS off in every user's Firefox,
  which is the point: DoH would otherwise resolve past the module entirely.
- Recompiling a filter list re-downloads every list, so the role only fires that handler when `get-web-filter` shows
  the filter actually moved.
- `ly` is built with Zig, downloaded from `desktop_zig_mirror` rather than from ziglang.org, whose donated
  bandwidth makes the origin download take about 20 minutes. Set it to a host listed in
  [community-mirrors.txt](https://ziglang.org/download/community-mirrors.txt); the archive is checksummed against
  the shasum the origin publishes.
