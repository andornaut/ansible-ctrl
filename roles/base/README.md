# ansible-role-base

Installs base packages and system configuration common to every Ubuntu host.

## Usage

Applied to every host by `base.yml`. `homeautomation.yml` and `webservers.yml` carry a commented-out `- base`
entry to uncomment on first run.

```bash
make base
make base -- --tags filectrl
```

## Variables

See [defaults/main.yml](./defaults/main.yml).

## Notes

- **Caps Lock is remapped to Escape on every host, in two places.** `XKBOPTIONS="caps:escape"` in
  `/etc/default/keyboard` covers the console and X11/Wayland sessions; GNOME builds its XKB config from dconf and
  ignores that file, so the same option is also written as a system-wide dconf default under
  `/etc/dconf/db/local.d/`. The key is not locked, so a user's own dconf setting still wins.
- **snap, cloud-init, and telemetry/crash-reporting are purged, then negatively pinned** via
  `/etc/apt/preferences.d/no-<name>` ([tasks/purge-and-pin.yml](./tasks/purge-and-pin.yml)). A negative pin is
  stronger than a dpkg hold: apt will not install the package even to satisfy another package's Recommends or
  Depends, and `apt dist-upgrade` removes any that slip back in. Purging snapd removes `ubuntu-server-minimal`
  (and `ubuntu-server` with it); purging apport keeps them out.
- **Leftover state is swept too**, since purging leaves per-user and installer state behind: user `snap/`
  directories, dangling snap systemd symlinks, `/etc/cloud`, `/var/lib/cloud`, and the `ubuntu-insights` consent
  and cache directories under every home.
- **Tools installed from GitHub releases** via
  [tasks/install_from_github.yml](./tasks/install_from_github.yml), which needs a
  `{name}_{system}_{base_arch}.tar.gz` release asset: [filectrl](https://github.com/andornaut/filectrl) (file
  manager), [gog](https://github.com/andornaut/gog), and [mrs](https://github.com/andornaut/mrs). Plus
  `cache-command` and [storage-space-alert](https://github.com/andornaut/storage-space-alert).
- **Cron** (`/etc/cron.d/ansible-role-base`): `storage-space-alert` hourly, `disk-cleanup` weekly.
- **Accounts are closed to each other** ([tasks/lockdown.yml](./tasks/lockdown.yml), tag `lockdown`): `UMASK 007`
  in `/etc/login.defs`, `HOME_MODE` and `adduser`'s `DIR_MODE` at `0750`, and `o-rwx` on every existing login
  account's home. Group access is untouched, `USERGROUPS_ENAB` giving each account a private group of its own and
  the roles that share a directory across accounts sharing it by group. A home with no world execute bit is a
  chokepoint, so nothing below it needs converging: a world-readable file deep in a home is unreachable once the
  home refuses traversal. `base_lockdown_exclude_homes` leaves a path alone; service accounts an installer created
  without `--system` land in the login uid range and are excluded by their `/nonexistent` home rather than by uid.
- **SSH accepts keys only** (same tag): `/etc/ssh/sshd_config.d/00-ansible-role-base.conf` sets
  `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `PubkeyAuthentication yes` and
  `PermitRootLogin no`. There is no opt-out flag. Instead the role proves, from the controller and as the account
  and address ansible itself connects with, that key-only SSH already works, and **fails the play** on a host
  where it does not, naming the `ssh-copy-id` to run first. Proving it beforehand is sufficient: withdrawing
  password authentication cannot break a key that already works, so there is nothing to roll back. A skip would
  instead leave a host that looks hardened and is not. The file is validated with `sshd -t` before it lands and
  applied with a reload, which established connections survive.

## Operations

```bash
# The negative pins and cron jobs the role installs
cat /etc/apt/preferences.d/no-*
cat /etc/cron.d/ansible-role-base

# Run the installed maintenance scripts by hand
storage-space-alert
sudo /usr/local/sbin/disk-cleanup
```
