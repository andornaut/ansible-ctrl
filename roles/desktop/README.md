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
| idle | Screen blanking, session locking and monitor power-off (dconf, [xscreensaver](https://www.jwz.org/xscreensaver/), [hypridle](https://github.com/hyprwm/hypridle)) |
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
| `desktop_xscreensaver_mode` | What `xscreensaver` draws once a bspwm session blanks (only `blank`: the hacks are not built) |
| `desktop_xscreensaver_dialog_theme` | Colour scheme for the unlock dialog (`borderlessblack`, `darkgray`, `default`, ...) |
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
- The idle timeouts are one policy with three mechanisms. GNOME reads dconf, bspwm delegates to `xscreensaver`, and
  niri to `hypridle`. Only X11 tells blanking apart from powering the monitor down, so bspwm honours all three
  timeouts, niri ignores the blank timeout, and GNOME ignores the power-off timeout.
- Under bspwm, `xscreensaver` owns blanking, locking and DPMS together. It takes over the X screensaver extension on
  startup, so `xset s` cannot coexist with it and the `idle` tag strips those lines from the session script.
  `xscreensaver`'s `lockTimeout` is a grace period measured from the moment the screen blanks, not from the start of
  idle, so it is the gap between the blank and lock timeouts, exactly like GNOME's `lock-delay`. It grabs the keyboard
  while blanked, and since 6.00 requires a click or a Shift tap before the prompt accepts input, so a password cannot
  be typed into the window underneath during that grace period.
- `xscreensaver` is built from source by the [bspwm](../bspwm/) role, into `/usr/local`. Ubuntu ships 6.08, an October
  2023 build. Only the driver is compiled; the several hundred screen hacks are not, which is why `mode` must stay
  `blank`.
- The unlock dialog's appearance is X **resources**, not `xscreensaver` preferences. `xscreensaver-auth` is an Xt
  program, so it merges `RESOURCE_MANAGER` over its compiled-in app-defaults, which is why the role writes them to
  `.Xresources` (merged by the session script's `xrdb -merge`) rather than to `.xscreensaver`. `dialogTheme` is the
  one exception: it is a preference. `xrdb` runs the file through `cpp`, so that managed block uses `!` markers, not
  `#`. The logo and the version heading cannot be removed: the logo is compiled in and `xscreensaver-auth` aborts
  without it, and the heading is a notice the author asks not to be removed.
- Idle **suspend** is a separate policy from idle locking, driven by `desktop_suspend_inactive_minutes`. `logind`
  cannot detect idleness itself: something must call `SetIdleHint`. GNOME uses `gnome-settings-daemon`
  (`sleep-inactive-{ac,battery}-{type,timeout}`); niri uses a `hypridle` listener that runs `systemctl suspend`
  itself. **bspwm has nothing**: `xscreensaver` never calls `SetIdleHint`, so `logind`'s `IdleAction` could never
  fire. Setting the variable on a bspwm host fails the play rather than writing a drop-in that does nothing.
- **Known issue**: `desktop_screen_*_minutes` and `desktop_suspend_inactive_minutes` are rendered into
  `.config/bspwm/desktop`, `.xscreensaver`, `.Xresources` and `.config/hypr/hypridle.conf`, which are symlinks into
  the shared dotfiles repository. Two hosts with different values would rewrite those managed blocks on every
  converge and fight over them in git. It is latent only because every host currently uses the same values. The fix
  is to stop rendering per-host policy into dotfiles: give the role a file it owns outright and leave the dotfiles
  copy free of host-specific values.
- The session files the `idle` tag writes (`.config/bspwm/desktop`, `.xscreensaver`, `.Xresources`,
  `.config/autostart/xscreensaver.desktop`, `.config/hypr/hypridle.conf`) may be symlinks into a dotfiles repository,
  which rules out `template` and `copy`: on a no-op run their action plugin re-runs the `file` module against the
  resolved link target, and `file` expands environment variables in that path, corrupting it for a repository whose
  tree lives under a directory named `$HOME`. `blockinfile`, `lineinfile` and `replace` resolve the link themselves
  and write through it, so the generated files are wrapped in an `ANSIBLE MANAGED BLOCK` rather than templated. A
  *dangling* link is a separate problem, and `stat` reports it as existing unless it too follows, so
  `idle_check_dotfile.yml` classifies each path first and fails with a clear message rather than orphaning the link.
- `xscreensaver` reloads `~/.xscreensaver` whenever it changes, so no handler restarts it. `.Xresources` is merged
  only at login, so dialog changes take effect at the next one.
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
