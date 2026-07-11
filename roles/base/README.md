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

| Variable | Default | Purpose |
| --- | --- | --- |
| `base_timezone` | `America/Toronto` | System timezone |
| `base_remap_capslock_to_escape` | `false` | Remap Caps Lock to Escape in `/etc/default/keyboard` |
| `base_arch` | derived | GoReleaser arch name (`amd64`/`arm64`) selecting the `gog` and `mrs` release assets |
| `base_cloud_init_packages` | `cloud-init`, `cloud-init-base` | Packages purged and negatively pinned |
| `base_snap_packages` | `snapd`, `gnome-software-plugin-snap` | Packages purged and negatively pinned |
| `base_telemetry_packages` | `apport`, `whoopsie`, `kerneloops`, ... | Packages purged and negatively pinned |

## Notes

- **Package purge and pin.** snap, cloud-init, and telemetry/crash-reporting are purged and then negatively
  pinned via `/etc/apt/preferences.d/no-<name>` (see [tasks/purge-and-pin.yml](./tasks/purge-and-pin.yml)). A
  negative pin is stronger than a dpkg hold: apt will not install the package even to satisfy another package's
  Recommends or Depends, and `apt dist-upgrade` removes any that slip back in. Purging snapd removes
  `ubuntu-server-minimal` (and `ubuntu-server` with it); purging apport keeps them out.
- **Leftover state.** Purging leaves per-user and installer state behind, so the role also sweeps user `snap/`
  directories and dangling snap systemd symlinks, `/etc/cloud` and `/var/lib/cloud`, and `ubuntu-insights`
  consent/cache directories under every home. `update-notifier-crash` units are masked for all users.
- **Installed tools.** [gog](https://github.com/andornaut/gog) and [mrs](https://github.com/andornaut/mrs) from
  GitHub releases (asset matched to `base_arch`), plus `cache-command` and
  [storage-space-alert](https://github.com/andornaut/storage-space-alert) fetched from raw GitHub.
- **Cron.** `storage-space-alert` runs hourly at `:30`; `disk-cleanup` runs weekly (`apt-get autoremove --purge`).
  Both live in `/etc/cron.d/ansible-role-base`.
- **systemd and journald.** Tightens `DefaultTimeout*`/`DefaultRestartSec`/`DefaultStartLimit*` in
  `system.conf`, and caps journald at 500M and 4 weeks.
- Also sets apt network timeouts, disables the ssh MOTD news banner, enables universe/multiverse (pre-24.04),
  and makes Vim the default editor.

## Operations

```bash
# The negative pins the role installs
cat /etc/apt/preferences.d/no-*

# The cron jobs the role installs
cat /etc/cron.d/ansible-role-base

# Run the installed maintenance scripts by hand
storage-space-alert
sudo /usr/local/sbin/disk-cleanup
```
