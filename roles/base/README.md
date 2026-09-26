# ansible-role-base

Installs base packages and system configuration common to every Ubuntu host.

## Usage

```bash
make base
make base -- --tags filectrl
```

`base.yml` applies this role to every host but the routers (`all:!routers`). On a new host it runs after
`make faramir` and before every other playbook, as [Usage](../../README.md#usage) orders them.

## Tags

| Tag                                               | Description                                                                                                                   |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| cloud-init                                        | Purges and pins `cloud-init`, and removes `/etc/cloud` and `/var/lib/cloud`                                                   |
| disk-cleanup                                      | The `disk-cleanup` sweep and its weekly cron entry                                                                            |
| fail2ban                                          | fail2ban and the sshd jail, from the `base_fail2ban_*` settings                                                               |
| [filectrl](https://github.com/andornaut/filectrl) | File manager, from its newest GitHub release                                                                                  |
| [gog](https://github.com/andornaut/gog)           | Dotfiles manager, from its newest GitHub release                                                                              |
| lockdown                                          | Home directory modes, the login umask, and key-only SSH on `base_lockdown_ssh_port`. See [Lockdown](#lockdown)                |
| [mrs](https://github.com/andornaut/mrs)           | Command line secrets manager, from its newest GitHub release                                                                  |
| rasdaemon                                         | Hardware error recording, gated on `base_install_rasdaemon`                                                                   |
| snap                                              | Purges and pins snapd, then removes the user directories and unit symlinks it leaves                                          |
| ssh-client                                        | The ssh client defaults every host shares: connect timeout, keepalives, GSSAPI                                                |
| storage-space-alert                               | The alert script and its hourly cron entry                                                                                    |
| sysctl                                            | `fs.inotify.max_user_watches`, from `base_inotify_max_user_watches`                                                           |
| systemd                                           | Unit timeout and restart defaults, journald retention, and the `/tmp` age at `base_tmp_max_age`                               |
| telemetry                                         | Purges and pins the telemetry and crash-reporting packages, removes the leftover user state, and masks the crash-report units |
| ubuntu-pro                                        | Turns off the apt-news fetch, leaving the client installed                                                                    |
| unwanted                                          | Purges and pins `base_unwanted_packages` ([vars/main.yml](./vars/main.yml))                                                   |

No tag: the apt configuration and package set, the motd-news opt-out,
the timezone, the Caps Lock remap, `cache-command` and the editor alternative. A `--tags` run skips them.

## Variables

See [defaults/main.yml](./defaults/main.yml).

| Variable                          | Purpose                                                                                              |
| --------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `base_timezone`                   | System timezone, an IANA name set through `community.general.timezone`. Default `America/Toronto`    |
| `base_lockdown_ssh_port`          | The sshd port, 22 by default. See [Lockdown](#lockdown)                                              |
| `base_lockdown_ssh_port_move`     | `true` for the one run that moves sshd off the inventory's `ansible_port`. See [Lockdown](#lockdown) |
| `base_account_exclude_homes`      | Placeholder homes of service accounts, excluded from the home-mode lockdown and the sweeps           |
| `base_install_rasdaemon`          | Hardware error recording, default `false`                                                            |
| `base_inotify_max_user_watches`   | Lower on a small host: each watch costs kernel memory                                                |
| `base_tmp_max_age`                | Age at which `/tmp` entries are removed                                                              |
| `base_ssh_client_connect_timeout` | Seconds the ssh client waits to connect                                                              |

## Installed files

| Path                                                                | Purpose                                                                                       |
| ------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `/etc/apt/apt.conf.d/99network-timeouts`                            | apt fetch timeouts and one retry                                                              |
| `/etc/apt/preferences.d/no-<name>`                                  | Negative pins of the purged packages ([tasks/purge-and-pin.yml](./tasks/purge-and-pin.yml))   |
| `/etc/cron.d/ansible-role-base`                                     | `storage-space-alert` hourly and `disk-cleanup` weekly                                        |
| `/usr/local/sbin/disk-cleanup`                                      | The weekly sweep                                                                              |
| `/usr/local/bin/storage-space-alert`, `cache-command`               | Single-file scripts from each repository's default branch                                     |
| `/usr/local/bin/filectrl`, `gog`, `mrs`                             | Tools from GitHub releases ([tasks/install_from_github.yml](./tasks/install_from_github.yml)) |
| `/etc/ssh/ssh_config.d/00-ansible-role-base.conf`                   | ssh client defaults                                                                           |
| `/etc/ssh/sshd_config.d/00-ansible-role-base.conf`                  | Key-only SSH                                                                                  |
| `/etc/ssh/sshd_config.d/00-ansible-role-base-port.conf`             | `base_lockdown_ssh_port`                                                                      |
| `/etc/fail2ban/jail.local`                                          | The sshd jail                                                                                 |
| `/etc/sysctl.d/60-ansible-role-base.conf`                           | `fs.inotify.max_user_watches`                                                                 |
| `/etc/tmpfiles.d/tmp.conf`                                          | `/tmp` age                                                                                    |
| `/etc/udev/rules.d/61-ansible-role-base-keyboard-caps-escape.rules` | Caps Lock remap at the device                                                                 |
| `/etc/dconf/profile/user`                                           | Adds the `local` system database to the default dconf profile                                 |
| `/etc/dconf/db/local.d/00-keyboard`                                 | Caps Lock remap for GNOME                                                                     |
| `/etc/systemd/user/update-notifier-crash.{path,service}`            | Masked, `/dev/null` links                                                                     |

## Shared task files

Three task files under [tasks/](./tasks) are entry points for the other roles, included by path so there is one
copy: `ansible.builtin.include_tasks: ../../base/tasks/<file>.yml`. The include inherits the caller's tags,
become and when like any `include_tasks`. The caller's `vars:` are the interface, so no input carries the calling
role's prefix.

| File                                                             | Purpose                                                                                                         |
| ---------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| [get_latest_release.yml](./tasks/get_latest_release.yml)         | Sets a fact to a repository's latest release. Inputs below                                                      |
| [require_tools.yml](./tasks/require_tools.yml)                   | `require_tools`: a list of `{name, probe, hint}`. Fails naming the tool and what installs it                    |
| [require_kernel_headers.yml](./tasks/require_kernel_headers.yml) | No inputs. Installs the headers DKMS builds against for the running kernel, and the metapackage that follows it |

`get_latest_release.yml` inputs:

| Input              | Detail                                                                                                                                        |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `release_repo`     | Required. `owner/repo`                                                                                                                        |
| `release_fact`     | Required. Name of the variable that receives the release object                                                                               |
| `release_api_base` | Optional. Default `https://api.github.com/repos`; a Forgejo forge such as Codeberg is `https://codeberg.org/api/v1/repos`                     |
| `release_stable`   | Optional. `true` takes the newest non-draft, non-prerelease entry of `/releases` instead of `/releases/latest`, and fails when none qualifies |
| `github_token`     | Not passed by the caller. Read from the inventory, where the broker injects it, and sent to `api.github.com` only                             |

| Constraint          | Detail                                                                                                                                   |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| One request per URL | Fetched once per play from the controller, for each distinct URL the hosts resolve. The fleet shares one address and one anonymous limit |
| Rate limit          | 60 requests an hour per address without `github_token`, 5000 per token with it                                                           |
| Rate-limit failure  | A 403 or 429 from the limit fails naming it, with `X-RateLimit-Remaining` and the reset time                                             |

## Lockdown

Tag `lockdown` ([tasks/lockdown.yml](./tasks/lockdown.yml)).

| Constraint             | Detail                                                                                                                                                                                                                                                          |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Home modes             | `HOME_MODE` and `adduser`'s `DIR_MODE` at `0710`, `o-rwx,g-r` on each login account's home. Nothing below the home is converged                                                                                                                                 |
| Subtractive only       | Ownership is never set. `USERGROUPS_ENAB` gives each account a private group, so the group bits reach only the owner until a home's group is shared, which then keeps traversal without listing                                                                 |
| Owned homes only       | A passwd entry naming a shared directory is left alone. `base_account_exclude_homes` excludes the placeholder homes of service accounts created without `--system`                                                                                              |
| Session umask          | `UMASK 002` in `/etc/login.defs`, read by `pam_umask` for login shells and SSH sessions. A default, not a boundary: a process may change it, and systemd units read `UMask=`                                                                                    |
| Why 002                | A file created in a setgid share stays group-writable, as the NAS share needs                                                                                                                                                                                   |
| Key-only SSH           | `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `PubkeyAuthentication yes`, `PermitRootLogin no`                                                                                                                                                |
| sshd config apply      | Validated with `sshd -t`, then reloaded, which established connections survive. Skipped where `ssh.service` is not running yet: `ssh.socket` starts it on the first connection, which reads the new config                                                      |
| No opt-out             | The role proves key-only SSH works from the controller with Ansible's own connection settings, and **fails the play** where it does not, naming the `ssh-copy-id` to run                                                                                        |
| SSH port               | Set in `sshd_config`, which `sshd-socket-generator` turns into `ssh.socket`'s `ListenStream` at `daemon-reload`                                                                                                                                                 |
| Port matches inventory | Asserted equal to `ansible_port` (22 when unset over SSH; unchecked on a local connection without one), so the proof cannot pass on a port the next run does not dial. To move it, run once with `base_lockdown_ssh_port_move=true`, then update `ansible_port` |
| Stray `Port` lines     | Cleared: sshd listens on every `Port` it reads                                                                                                                                                                                                                  |
| Host key pin           | Before the port moves, the host's keys are pinned on the controller under the name ssh looks them up by: the bare address on 22, `[host]:port` otherwise                                                                                                        |

## Notes

| Constraint               | Detail                                                                                                                                                                                                                    |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Caps Lock remap          | Escape, in three places. `XKBOPTIONS="caps:escape"` in `/etc/default/keyboard` covers the console and X11/Wayland sessions                                                                                                |
| GNOME remap              | GNOME builds its XKB config from dconf and ignores `/etc/default/keyboard`, so the option is also a system dconf default                                                                                                  |
| Device remap             | Both of the above act on the keysym; a program reading raw scan codes still sees Caps Lock. The udev rule remaps it at the device, on devices `input_id` classifies as keyboards                                          |
| Device remap scope       | The HID usage on USB and Bluetooth, the AT scan code on PS/2. It acts below every session, so no user setting restores Caps Lock                                                                                          |
| Negative pins            | snap, cloud-init, telemetry and crash reporting, and the `unwanted` set are purged, then pinned at a negative priority                                                                                                    |
| Pin versus hold          | apt will not install a pinned package even for another's Recommends or Depends, and `apt dist-upgrade` removes any that return. A dpkg hold does neither                                                                  |
| snapd and apport         | Purging snapd removes `ubuntu-server-minimal` and `ubuntu-server` with it; purging apport keeps them out                                                                                                                  |
| Leftover state           | User `snap/` directories, dangling snap systemd symlinks, `/etc/cloud`, `/var/lib/cloud`, and the `ubuntu-insights` consent and cache directories under every home                                                        |
| Which homes              | From passwd, not a listing of `/home` ([tasks/account_homes.yml](./tasks/account_homes.yml)), so a home outside `/home` is included                                                                                       |
| Skipped homes            | A home the account does not own is a shared area and is left alone. A home passwd names that does not exist is dropped before `find` runs                                                                                 |
| Unwanted set             | Ubuntu defaults no host here has hardware or a role for. In [vars/main.yml](./vars/main.yml), so a host cannot opt out                                                                                                    |
| Unwanted members         | `kdump-tools` (reserves memory at boot through GRUB's `crashkernel=`, returned at the next reboot), `modemmanager`, `power-profiles-daemon`, `switcheroo-control`, `open-vm-tools`, `pollinate`, `sssd` and `sssd-common` |
| Desktop dependencies     | Nothing a desktop metapackage depends on belongs in the set: pinning `language-selector-gnome` removes gdm3, gnome-shell and ubuntu-session. `speech-dispatcher` stays out: the desktop role installs it for Firefox      |
| GitHub release tools     | filectrl, gog and mrs need a `{name}_{system}_{base_arch}.tar.gz` asset, checked against the SHA-256 digest GitHub records for it. An asset without one fails the run                                                     |
| Default-branch scripts   | cache-command and storage-space-alert come from each repository's default branch. No version is pinned, so every run takes the current file                                                                               |
| inotify watches          | Ubuntu derives a default from RAM that is below what an editor or file sync needs for a large source tree. A ceiling, not an allocation                                                                                   |
| `fs.file-max`            | Not set: the kernel leaves it effectively unbounded, so setting it could only lower it                                                                                                                                    |
| `/tmp` age               | Overrides the shipped 30d, at which a desktop's `/tmp` reaches several GB. `systemd-tmpfiles-clean.timer` applies it daily and removes a directory once its contents age out                                              |
| `/tmp` floor             | Not shorter: a tmux server's socket and a forwarded ssh-agent socket live in `/tmp` with no protecting entry of their own                                                                                                 |
| Unit start limit         | `DefaultStartLimitBurst=3` counts the first start, so with `DefaultRestartSec=30` inside `DefaultStartLimitIntervalSec=120` a unit that fails on every start stops after its second restart instead of restarting forever |
| Ubuntu Pro               | Purging the pro client removes `update-notifier`, which writes `/var/run/reboot-required`. Disabling apt-news stops the per-apt-run fetch and the `ubuntu_pro_apt_news` AppArmor denials                                  |
| ssh client timeout       | It applies to ssh started outside Ansible (cron); Ansible passes its own timeout. Without it, a host that is off costs the full TCP retry, about 135 seconds per connection                                               |
| ssh client config order  | Validated with `ssh -G` first. `ssh_config` keeps the first value it finds and the `Include` precedes the shipped `Host *`, so this overrides the defaults and `~/.ssh/config` overrides this                             |
| ssh client timeout scope | Bounds the connect and banner exchange only, not authentication, and not an sshd that accepts and then stalls                                                                                                             |
| Weekly sweep             | `disk-cleanup` also deletes rotated and compressed logs under `/var/log`, leaving the live files logrotate writes, and clears every account's `~/.cache/thumbnails`                                                       |
| Flatpak sweep            | `flatpak uninstall --unused` acts on the caller's installation. Each account with `~/.local/share/flatpak` is swept under `runuser`, with `HOME` set because `runuser` does not                                           |
| rasdaemon                | Persists machine-check exceptions to `/var/lib/rasdaemon`, read with `ras-mc-ctl --errors`. Enable per host in `host_vars`                                                                                                |
| rasdaemon default off    | The memory-error half needs an EDAC memory controller, which non-ECC hardware does not register, and the daemon logs a failure for each trace class the hardware lacks                                                    |
| `ras-mc-ctl` on 0.8.4    | The machine-check section fails with a `DBD::SQLite` error: it selects a `signal` column the `mce_record` schema lacks. The records are written; read them with `sqlite3`                                                 |

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

# The machine-check records, which the command above cannot print on rasdaemon 0.8.4
sudo sqlite3 /var/lib/rasdaemon/ras-mc_event.db 'select * from mce_record'
```
