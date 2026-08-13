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

| What | Detail |
| --- | --- |
| Caps Lock is remapped to Escape, in two places | `XKBOPTIONS="caps:escape"` in `/etc/default/keyboard` covers the console and X11/Wayland sessions; GNOME builds its XKB config from dconf and ignores that file, so the option is also a system-wide dconf default under `/etc/dconf/db/local.d/`. The key is not locked, so a user's own setting still wins |
| snap, cloud-init and telemetry/crash-reporting are purged, then negatively pinned via `/etc/apt/preferences.d/no-<name>` ([tasks/purge-and-pin.yml](./tasks/purge-and-pin.yml)) | A negative pin is stronger than a dpkg hold: apt will not install the package even to satisfy another's Recommends or Depends, and `apt dist-upgrade` removes any that slip back in. Purging snapd removes `ubuntu-server-minimal` (and `ubuntu-server` with it); purging apport keeps them out |
| Leftover state is swept | Purging leaves per-user and installer state: user `snap/` directories, dangling snap systemd symlinks, `/etc/cloud`, `/var/lib/cloud`, and the `ubuntu-insights` consent and cache directories under every home |
| Tools from GitHub releases, via [tasks/install_from_github.yml](./tasks/install_from_github.yml) | [filectrl](https://github.com/andornaut/filectrl) (file manager), [gog](https://github.com/andornaut/gog), [mrs](https://github.com/andornaut/mrs), `cache-command`, [storage-space-alert](https://github.com/andornaut/storage-space-alert). Needs a `{name}_{system}_{base_arch}.tar.gz` release asset |
| Cron, in `/etc/cron.d/ansible-role-base` | `storage-space-alert` hourly, `disk-cleanup` weekly |

Tag `lockdown` ([tasks/lockdown.yml](./tasks/lockdown.yml)):

| What | Detail |
| --- | --- |
| Accounts are closed to each other | `UMASK 007` in `/etc/login.defs`, `HOME_MODE` and `adduser`'s `DIR_MODE` at `0750`, `o-rwx` on each login account's home. Group access is untouched: `USERGROUPS_ENAB` gives each account a private group, and what is shared across accounts is shared by group. A home with no world execute bit is a chokepoint, so nothing below it needs converging |
| A home is closed only when its account owns it | So a passwd entry naming a shared directory is left alone, and `base_lockdown_exclude_homes` excludes the placeholder homes that service accounts created without `--system` point at |
| SSH accepts keys only | `sshd_config.d/00-ansible-role-base.conf` sets `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `PubkeyAuthentication yes`, `PermitRootLogin no`. Validated with `sshd -t` before it lands, applied with a reload that established connections survive |
| No opt-out flag | The role proves key-only SSH already works, from the controller and with ansible's own connection settings, and **fails the play** where it does not, naming the `ssh-copy-id` to run. A skip would leave a host that looks hardened and is not |
| The SSH port is `base_lockdown_ssh_port`, 22 unless `host_vars` names another | Set through `sshd_config`, which `sshd-socket-generator` turns into `ssh.socket`'s `ListenStream` at `daemon-reload`. A `Port` left anywhere else is cleared, sshd accumulating them rather than taking the first. Before the port moves, the host's keys are pinned on the controller under the name ssh looks them up by: the bare address on 22, `[host]:port` otherwise |

## Operations

```bash
# The negative pins and cron jobs the role installs
cat /etc/apt/preferences.d/no-*
cat /etc/cron.d/ansible-role-base

# Run the installed maintenance scripts by hand
storage-space-alert
sudo /usr/local/sbin/disk-cleanup
```
