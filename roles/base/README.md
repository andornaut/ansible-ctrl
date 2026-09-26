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

| Tag                                               | Description                                                                                  |
| ------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| cloud-init                                        | Purges and pins `cloud-init`, and removes its state                                          |
| disk-cleanup                                      | The `disk-cleanup` sweep and its weekly cron entry                                           |
| fail2ban                                          | fail2ban and the sshd jail, from the `base_fail2ban_*` settings                              |
| [filectrl](https://github.com/andornaut/filectrl) | File manager, from its newest GitHub release                                                 |
| [gog](https://github.com/andornaut/gog)           | Dotfiles manager, from its newest GitHub release                                             |
| lockdown                                          | Home directory modes, the login umask, and key-only SSH. See [Lockdown](#lockdown)           |
| [mrs](https://github.com/andornaut/mrs)           | Command line secrets manager, from its newest GitHub release                                 |
| rasdaemon                                         | Hardware error recording, gated on `base_install_rasdaemon`                                  |
| snap                                              | Purges and pins snapd, and removes what it leaves behind                                     |
| ssh-client                                        | ssh client defaults: connect timeout, keepalives, GSSAPI                                     |
| storage-space-alert                               | The alert script and its hourly cron entry                                                   |
| sysctl                                            | `fs.inotify.max_user_watches`, from `base_inotify_max_user_watches`                          |
| systemd                                           | Unit timeout and restart defaults, journald retention, and the `/tmp` age                    |
| telemetry                                         | Purges and pins the telemetry and crash-reporting packages, and masks the crash-report units |
| ubuntu-pro                                        | Turns off the apt-news fetch, leaving the client installed                                   |
| unwanted                                          | Purges and pins `base_unwanted_packages` ([vars/main.yml](./vars/main.yml))                  |

No tag: the apt configuration and package set, the motd-news opt-out, the timezone, the Caps Lock remap,
`cache-command` and the editor alternative. A `--tags` run skips them.

## Variables

See [defaults/main.yml](./defaults/main.yml).

| Variable                      | Purpose                                                                                              |
| ----------------------------- | ---------------------------------------------------------------------------------------------------- |
| `base_lockdown_ssh_port`      | The sshd port, 22 by default. See [Lockdown](#lockdown)                                              |
| `base_lockdown_ssh_port_move` | `true` for the one run that moves sshd off the inventory's `ansible_port`. See [Lockdown](#lockdown) |
| `base_account_exclude_homes`  | Placeholder homes of service accounts, excluded from the home-mode lockdown and the sweeps           |

## Shared task files

Three task files under [tasks/](./tasks) are entry points for the other roles, included by path:
`ansible.builtin.include_tasks: ../../base/tasks/<file>.yml`. The caller's `vars:` are the interface, so no input
carries the calling role's prefix.

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
| `github_token`     | Not passed by the caller. Read from the inventory and sent to `api.github.com` only                                                           |

Each URL is fetched once per play from the controller. Without `github_token` the fleet shares one anonymous limit
of 60 requests an hour; a rate-limit failure names the reset time.

## Lockdown

| Constraint             | Detail                                                                                                                                                                                           |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Home modes             | `0710` for new homes and `o-rwx,g-r` on each login account's existing home. Nothing below the home is changed, and a home the account does not own is left alone                                 |
| Session umask          | `002`, so a file created in a setgid share stays group-writable. A default, not a boundary                                                                                                       |
| Key-only SSH           | Password and keyboard-interactive authentication off, root login off                                                                                                                             |
| No opt-out             | The role checks that key-only SSH works from the controller and **fails the play** where it does not, naming the `ssh-copy-id` to run                                                            |
| Port matches inventory | `base_lockdown_ssh_port` must equal `ansible_port`. To move it, run once with `base_lockdown_ssh_port_move=true`, then update `ansible_port`. The host's keys are pinned on the controller first |

## Notes

| Constraint             | Detail                                                                                                                                                                 |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Caps Lock remap        | Escape, at the console, in X11 and Wayland sessions, in GNOME, and at the device for programs reading raw scan codes. No user setting restores Caps Lock               |
| Purged packages        | snap, cloud-init, telemetry, crash reporting and the `unwanted` set are pinned at a negative priority, so apt will not reinstall them as another's dependency          |
| Unwanted set           | In [vars/main.yml](./vars/main.yml), so a host cannot opt out. Nothing a desktop metapackage depends on belongs in it                                                  |
| Default-branch scripts | cache-command and storage-space-alert are unpinned; every run takes the current file                                                                                   |
| Weekly sweep           | `disk-cleanup` also deletes rotated logs under `/var/log`, every account's thumbnail cache and unused flatpak runtimes                                                 |
| Unit start limit       | A unit that fails on every start stops after its second restart                                                                                                        |
| ssh client timeout     | Applies to ssh started outside Ansible (cron). Bounds the connect and banner exchange only                                                                             |
| rasdaemon              | Off by default: it needs an EDAC memory controller, which non-ECC hardware lacks. On 0.8.4 `ras-mc-ctl`'s machine-check section fails; read the records with `sqlite3` |

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
