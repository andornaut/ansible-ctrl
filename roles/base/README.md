# ansible-role-base

Installs base packages and system configuration common to every Ubuntu host.

## Usage

Applied to every host but the routers by `base.yml` (`all:!routers`). `homeautomation.yml` and `webservers.yml` carry a commented-out `- base`
entry to uncomment on a host's first run.

```bash
make base
make base -- --tags filectrl
```

## Tags

| Tag | Description |
| --- | --- |
| cloud-init | Purges and pins `cloud-init`, and removes `/etc/cloud` and `/var/lib/cloud` |
| disk-cleanup | The `disk-cleanup` sweep and its weekly cron entry |
| fail2ban | fail2ban and the sshd jail, from the `base_fail2ban_*` settings |
| [filectrl](https://github.com/andornaut/filectrl) | File manager, from its newest GitHub release |
| [gog](https://github.com/andornaut/gog) | Dotfiles manager, from its newest GitHub release |
| lockdown | Home directory modes, the login umask, and key-only SSH on `base_lockdown_ssh_port` |
| [mrs](https://github.com/andornaut/mrs) | Command line secrets manager, from its newest GitHub release |
| rasdaemon | Hardware error recording, gated on `base_install_rasdaemon` |
| snap | Purges and pins snapd, then sweeps the user directories and unit symlinks it leaves |
| ssh-client | The ssh client defaults every host shares: connect timeout, keepalives, GSSAPI |
| storage-space-alert | The alert script and its hourly cron entry |
| sysctl | `fs.inotify.max_user_watches`, from `base_inotify_max_user_watches` |
| systemd | Unit timeout and restart defaults, journald retention, and the `/tmp` age at `base_tmp_max_age` |
| telemetry | Purges and pins the telemetry and crash-reporting packages, sweeps the leftover user state, and masks the crash-report units |
| ubuntu-pro | Turns off the apt-news fetch, leaving the client installed |
| unwanted | Purges and pins `base_unwanted_packages` ([vars/main.yml](./vars/main.yml)) |

The apt package set, the timezone, the Caps Lock remap, `cache-command` and the editor alternative carry no tag,
so a `--tags` run skips them.

## Variables

See [defaults/main.yml](./defaults/main.yml).

## Notes

| What | Detail |
| --- | --- |
| Caps Lock is remapped to Escape, in two places | `XKBOPTIONS="caps:escape"` in `/etc/default/keyboard` covers the console and X11/Wayland sessions; GNOME builds its XKB config from dconf and ignores that file, so the option is also a system-wide dconf default under `/etc/dconf/db/local.d/`. The key is not locked, so a user's own setting still wins |
| snap, cloud-init, telemetry/crash-reporting and a set of unwanted defaults are purged, then negatively pinned via `/etc/apt/preferences.d/no-<name>` ([tasks/purge-and-pin.yml](./tasks/purge-and-pin.yml)) | A negative pin is stronger than a dpkg hold: apt will not install the package even to satisfy another's Recommends or Depends, and `apt dist-upgrade` removes any that slip back in. Purging snapd removes `ubuntu-server-minimal` and `ubuntu-server` with it; purging apport keeps them out |
| Leftover state is swept | User `snap/` directories, dangling snap systemd symlinks, `/etc/cloud`, `/var/lib/cloud`, and the `ubuntu-insights` consent and cache directories under every home |
| The homes a sweep reaches come from passwd, not from a listing of `/home` ([tasks/account_homes.yml](./tasks/account_homes.yml)) | Root's home and every login account's are swept wherever passwd names them, so a home outside `/home` is not missed. A home the account does not own names a shared area and is left alone, and a home passwd names that the host does not have is dropped before `find` sees it |
| Tools from GitHub releases, via [tasks/install_from_github.yml](./tasks/install_from_github.yml) | [filectrl](https://github.com/andornaut/filectrl) (file manager), [gog](https://github.com/andornaut/gog) and [mrs](https://github.com/andornaut/mrs). Needs a `{name}_{system}_{base_arch}.tar.gz` release asset |
| Single-file scripts fetched from a repository's default branch rather than from a release | [cache-command](https://github.com/andornaut/cache-command) and [storage-space-alert](https://github.com/andornaut/storage-space-alert), each downloaded into `/usr/local/bin`. Nothing pins a version, so every run takes the current file |
| The `unwanted` set ([vars/main.yml](./vars/main.yml)) is what Ubuntu installs by default and no host here has hardware or a role for | `kdump-tools` (crash dumps nobody reads, and it reserves memory at boot through GRUB's `crashkernel=`, returned at the next reboot), `modemmanager` (no modems), `power-profiles-daemon` and `switcheroo-control` (no laptop power profiles or dual-GPU switching), `open-vm-tools` (VMware guest tools on bare metal), `pollinate` (one-shot entropy seeding), and `sssd` with `sssd-common` (no directory service). In `vars/`, so a host cannot opt out of a purge set. Nothing a desktop metapackage depends on belongs in it: pinning `language-selector-gnome` takes gdm3, gnome-shell and ubuntu-session with it, and `speech-dispatcher` returns through the same tree |
| `fs.inotify.max_user_watches` is set from `base_inotify_max_user_watches` ([tasks/sysctl.yml](./tasks/sysctl.yml)) | Ubuntu derives a default from RAM, which lands well below what an editor or file-syncing tool needs for a large source tree. A ceiling rather than an allocation, but each watch costs kernel memory, so a small host should lower it in `host_vars`. `fs.file-max` is deliberately not set: the kernel already leaves it effectively unbounded and naming it could only lower it |
| `/tmp` is aged at `base_tmp_max_age` ([tasks/systemd.yml](./tasks/systemd.yml)) | `/etc/tmpfiles.d/tmp.conf` overrides the shipped 30d, which is long enough for a desktop's `/tmp` to reach several GB before anything is collected. Not shorter: a tmux server's socket and a forwarded ssh-agent socket live in `/tmp` with no protecting entry of their own. `systemd-tmpfiles-clean.timer` applies it daily and only removes a directory once its contents have aged out |
| Ubuntu Pro stays installed, but its apt-news fetch is turned off ([tasks/ubuntu-pro.yml](./tasks/ubuntu-pro.yml)) | Purging the pro client takes `update-notifier` with it, and that is what writes `/var/run/reboot-required`. Disabling apt-news stops the per-apt-run network fetch and the `ubuntu_pro_apt_news` AppArmor denials without losing reboot detection |
| The ssh client waits `base_ssh_client_connect_timeout` seconds to connect ([tasks/ssh-client.yml](./tasks/ssh-client.yml)) | `/etc/ssh/ssh_config.d/00-ansible-role-base.conf`, validated with `ssh -G` before it lands because every ssh on the host reads it. This is for the ssh no ansible run invokes, ansible passing a timeout of its own: cron, where a host that is merely off otherwise costs the full TCP retry, about 135 seconds per connection. `ssh_config` keeps the first value it finds and the `Include` sits above the shipped `Host *`, so this outranks the defaults while a user's `~/.ssh/config` still outranks it. Bounds the connect and banner exchange only, not authentication and not an sshd that accepts and then stalls |
| Cron, in `/etc/cron.d/ansible-role-base` | `storage-space-alert` hourly, `disk-cleanup` weekly. The weekly sweep also deletes rotated and compressed logs under `/var/log`, leaving the live files logrotate is still writing, and clears every account's `~/.cache/thumbnails` |
| `disk-cleanup` sweeps flatpak once per installation, not once per host | `flatpak uninstall --unused` acts on the installation of whoever runs it, so the root run reaches only the system one. On a desktop the runtimes are almost entirely per-user under `$HOME/.local/share/flatpak`, so every account with such a directory is passed over separately under `runuser`, with `HOME` named because `runuser` does not set it |
| Hardware errors are recorded past the journal's vacuum, where `base_install_rasdaemon` asks for it | `rasdaemon` persists machine-check exceptions to `/var/lib/rasdaemon`, read back with `ras-mc-ctl --errors`. Off by default: the memory-error half needs an EDAC memory controller, which non-ECC hardware does not register, and the daemon logs a failure for each trace class the hardware lacks. The CPU's machine-check records work regardless, so enable it per host in `host_vars` where those are wanted |
| `ras-mc-ctl --errors` cannot print its machine-check section on rasdaemon 0.8.4 | It selects a `signal` column that is absent from the `mce_record` schema the same version creates, so that section fails with a `DBD::SQLite` error while the memory, PCIe, ARM and CXL sections report normally. The records are still written. Read them with `sqlite3 /var/lib/rasdaemon/ras-mc_event.db 'select * from mce_record'` |

Tag `lockdown` ([tasks/lockdown.yml](./tasks/lockdown.yml)):

| What | Detail |
| --- | --- |
| Accounts are closed to each other | `HOME_MODE` and `adduser`'s `DIR_MODE` at `0710`, `o-rwx,g-r` on each login account's home. Nothing below the home needs converging. Subtractive only, and ownership is never set: `USERGROUPS_ENAB` gives each account a private group, so the group bits reach nobody but the owner until a home's group is deliberately shared, and a shared group keeps the traversal it needs without a listing |
| A session's default modes | `UMASK 002` in `/etc/login.defs`, read by `pam_umask` for login shells and SSH sessions. A default, not a boundary: a process may change it, and systemd units read `UMask=` instead. 002 keeps a file created in a setgid share group-writable, as the NAS share and others like it need |
| A home is closed only when its account owns it | A passwd entry naming a shared directory is left alone, and `base_account_exclude_homes` excludes the placeholder homes that service accounts created without `--system` point at |
| SSH accepts keys only | `sshd_config.d/00-ansible-role-base.conf` sets `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `PubkeyAuthentication yes`, `PermitRootLogin no`. Validated with `sshd -t` before it lands, applied with a reload that established connections survive, skipped where `ssh.service` is not running, as under socket activation |
| No opt-out flag | The role proves key-only SSH already works, from the controller and with ansible's own connection settings, and **fails the play** where it does not, naming the `ssh-copy-id` to run |
| The SSH port is `base_lockdown_ssh_port`, 22 unless `host_vars` names another | Set through `sshd_config`, which `sshd-socket-generator` turns into `ssh.socket`'s `ListenStream` at `daemon-reload`. A `Port` left anywhere else is cleared, sshd accumulating them rather than taking the first. Before the port moves, the host's keys are pinned on the controller under the name ssh looks them up by: the bare address on 22, `[host]:port` otherwise |

## Operations

```bash
# The negative pins and cron jobs the role installs
cat /etc/apt/preferences.d/no-*
cat /etc/cron.d/ansible-role-base

# Run the installed maintenance scripts by hand
storage-space-alert
sudo /usr/local/sbin/disk-cleanup

# Hardware errors rasdaemon has recorded
ras-mc-ctl --errors

# The machine-check records, which the command above cannot print
sudo sqlite3 /var/lib/rasdaemon/ras-mc_event.db 'select * from mce_record'
```
