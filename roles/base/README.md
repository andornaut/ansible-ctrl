# ansible-role-base

Installs base packages and system configuration common to every Ubuntu host.

## Usage

```bash
make base
```

Applied to every host by `base.yml`. `homeautomation.yml` and `webservers.yml` carry a commented-out `- base`
entry to uncomment on first run.

## Variables

See [defaults/main.yml](./defaults/main.yml).

| Variable | Purpose |
| --- | --- |
| `base_timezone` | System timezone |
| `base_remap_capslock_to_escape` | Remap Caps Lock to Escape in `/etc/default/keyboard` |

## Notes

- **Package purge and pin.** snap, cloud-init, and telemetry/crash-reporting are purged, then negatively pinned
  via `/etc/apt/preferences.d/no-<name>` ([tasks/purge-and-pin.yml](./tasks/purge-and-pin.yml)). A negative pin is
  stronger than a dpkg hold: apt will not install the package even to satisfy another package's Recommends or
  Depends, and `apt dist-upgrade` removes any that slip back in. Purging snapd removes `ubuntu-server-minimal`
  (and `ubuntu-server` with it); purging apport keeps them out.
- **Leftover state.** Purging leaves per-user and installer state behind, so the role also sweeps user `snap/`
  directories, dangling snap systemd symlinks, `/etc/cloud` and `/var/lib/cloud`, and the `ubuntu-insights`
  consent and cache directories under every home.
- **Installed tools.** [gog](https://github.com/andornaut/gog) and [mrs](https://github.com/andornaut/mrs) from
  GitHub releases (asset matched to `base_arch`), plus `cache-command`,
  [filectrl](https://github.com/andornaut/filectrl) (file manager), and
  [storage-space-alert](https://github.com/andornaut/storage-space-alert).
- **Cron.** `storage-space-alert` runs hourly and `disk-cleanup` weekly, both from
  `/etc/cron.d/ansible-role-base`.

## Operations

```bash
# The negative pins and cron jobs the role installs
cat /etc/apt/preferences.d/no-*
cat /etc/cron.d/ansible-role-base

# Run the installed maintenance scripts by hand
storage-space-alert
sudo /usr/local/sbin/disk-cleanup
```
