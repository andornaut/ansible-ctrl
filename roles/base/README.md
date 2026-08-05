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

## Operations

```bash
# The negative pins and cron jobs the role installs
cat /etc/apt/preferences.d/no-*
cat /etc/cron.d/ansible-role-base

# Run the installed maintenance scripts by hand
storage-space-alert
sudo /usr/local/sbin/disk-cleanup
```
