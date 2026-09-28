# ansible-role-rsnapshot

Installs [rsnapshot](https://rsnapshot.org/) and its cron jobs for automated incremental backups.

## Usage

```bash
make rsnapshot
```

## Tags

No tags.

## Variables

See [defaults/main.yml](./defaults/main.yml).

| Variable                               | Purpose                                                                                                                                                       |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `rsnapshot_hosts`                      | Hosts, directories, and backup scripts to snapshot. Required                                                                                                  |
| `rsnapshot_directory`                  | Snapshot root                                                                                                                                                 |
| `rsnapshot_preexec_script`             | Where the mountpoint check and the wake are installed                                                                                                         |
| `rsnapshot_required_mountpoints`       | Blocking mountpoints: checked by the play and before the lowest interval, and one missing aborts the run. Empty installs no check                             |
| `rsnapshot_nonblocking_mountpoints`    | Required mountpoints whose absence skips only the local points under them and reports an error, while the rest of the run continues. Empty installs no script |
| `rsnapshot_nonblocking_sources_script` | Where the command printing those points is installed                                                                                                          |
| `rsnapshot_wake_timeout`               | Seconds to wait for a woken host to answer ssh before the run goes on without it                                                                              |
| `rsnapshot_retention`                  | Snapshots kept per interval. Null or 0 omits both the `retain` line and the cron job                                                                          |
| `rsnapshot_schedule`                   | Cron time per interval, keyed to match `rsnapshot_retention`. Longer intervals run first                                                                      |

Each entry in `rsnapshot_hosts` takes `name`, `host`, and at least one of `directories` (trailing
slash required by rsnapshot) or `scripts` (each a `command` path and optional `args`), plus these
optional keys:

| Key    | Purpose                                                                                                                                |
| ------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| `name` | The address rsync dials and the directory the snapshot lands in. Required                                                              |
| `host` | Inventory name of the host. Required: it decides the login account, whether the point is read locally, and whether the login escalates |
| `user` | Login account. Default: the `ansible_user` of `host`, then `primary_user`                                                              |
| `wake` | `router` (inventory name of a pfSense router), `mac` and `broadcast`: wakes the host before the lowest interval reads its sources      |

| Condition                           | Effect                                                |
| ----------------------------------- | ----------------------------------------------------- |
| `host` is the host running the role | Read from the local filesystem                        |
| Login account is `root`             | Pulled over SSH with no escalation                    |
| Any other login account             | Pulled over SSH, running the remote rsync with `sudo` |

A path naming an account belongs to the host being backed up, so write it through that host's `hostvars` (as below).
A bare `{{ primary_user }}` resolves on the host running rsnapshot. Role defaults are absent from `hostvars`.

A directory may be a mapping of `path` and `exclude` (a list of patterns) instead of a plain path.

```yaml
rsnapshot_hosts:
  - name: example.com
    host: example
    # Woken over its wired NIC before the backup. Left awake afterwards.
    wake:
      router: router-example
      mac: "00:11:22:33:44:55"
      broadcast: 192.168.2.255
    directories:
      - /etc/
      - "/home/{{ hostvars['example'].primary_user }}/.ssh/"
      - "/home/{{ hostvars['example'].desktop_user }}/.gnupg/"
      - path: /var/docker-volumes/
        exclude:
          - cache/
    scripts:
      - command: /usr/local/bin/backupdockerpostgresql
        args: --host {{ hostvars['example'].primary_user }}@example.com --container postgresql postgresql.gz

  - name: router.example.com
    host: router-example
    directories:
      - /conf/config.xml

rsnapshot_required_mountpoints:
  - /media/nas

# An ecryptfs home, mounted only while its user is logged in: required, but its absence
# must not stop the other backups.
rsnapshot_nonblocking_mountpoints:
  - "/home/{{ primary_user }}"

rsnapshot_retention:
  hourly:
  daily: 7
  weekly: 4
  monthly: 12
```

## Installed files

| Path                                                                                    | Purpose                                                                                                                       |
| --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `/etc/rsnapshot.conf`                                                                   | Rendered from `rsnapshot_hosts` and validated with `rsnapshot configtest`                                                     |
| `rsnapshot_preexec_script` (`/usr/local/bin/rsnapshot-preexec`)                         | The mountpoint check and the wake. Only with `rsnapshot_required_mountpoints` or a `wake` entry                               |
| `rsnapshot_nonblocking_sources_script` (`/usr/local/bin/rsnapshot-nonblocking-sources`) | Prints the points under each mounted `rsnapshot_nonblocking_mountpoints` entry. Only with `rsnapshot_nonblocking_mountpoints` |
| `/usr/local/bin/backupmysql`, `/usr/local/bin/backupdockerpostgresql`                   | Backup scripts for use as `scripts`                                                                                           |
| `/etc/cron.d/ansible-role-rsnapshot`                                                    | One job per retention interval, run as root                                                                                   |

## Notes

| Constraint                         | Detail                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Local entry directories must exist | The role fails if a directory of the local entry does not exist. One under an unmounted `rsnapshot_nonblocking_mountpoints` entry is not checked                                                                                                                                                                                                                                                                                                 |
| Non-blocking mountpoints           | Unmounted, that entry's local points are skipped (tested with `mountpoint -q`, so an unmounted ecryptfs home's stub files are never stored) and cron mails root `ERROR: <mountpoint> is not mounted; its backup points were skipped` once per interval run. The newest snapshot keeps the last mounted copy. A mountpoint listed in both lists fails the play                                                                                    |
| Snapshot root                      | The play and the lowest interval's cron run both fail while a `rsnapshot_required_mountpoints` path is unmounted, rather than writing onto the filesystem beneath                                                                                                                                                                                                                                                                                |
| Snapshot layout                    | `rsnapshot_directory/{interval}.{n}/` (`.0` is newest): directories in `{name}/`, script output in `{name}_{script}/`                                                                                                                                                                                                                                                                                                                            |
| Disk usage                         | Unchanged files are hard-linked between snapshots, so `du` over the whole root overstates usage. A file rewritten between runs is stored in full each time                                                                                                                                                                                                                                                                                       |
| Interval order                     | Keep longer intervals scheduled a few minutes before shorter ones when overriding `rsnapshot_schedule`: an interval that finds the lockfile held exits without rotating                                                                                                                                                                                                                                                                          |
| `exclude` patterns                 | May contain spaces but not a double quote. `--delete-excluded` is in force, so a pattern added later also drops what earlier runs stored                                                                                                                                                                                                                                                                                                         |
| Root's key                         | The cron runs as root, so root's key on the host running the role must be authorized for each remote point's login account. Nothing distributes it; a missing one shows as `rsync returned 255` in `/var/log/rsnapshot.log`                                                                                                                                                                                                                      |
| Wake                               | A host that already answers ssh gets no packet. Otherwise root sshes to the `router`, which runs `wol -i <broadcast> <mac>` onto the host's subnet, and the run waits up to `rsnapshot_wake_timeout` for ssh. A host that stays asleep is mailed as an error and fails only its own points. The host needs wake-on-LAN armed on that NIC and its firmware allowing PCIe wake, and root's key authorized on the router. Nothing suspends it again |
| pfSense `authorized_keys2`         | On a pfSense target put the key in `authorized_keys2`: `authorized_keys` is regenerated on boot and on every user save                                                                                                                                                                                                                                                                                                                           |

## Operations

```bash
# Validate /etc/rsnapshot.conf
sudo rsnapshot configtest

# Show the rsync commands an interval would run, without running them
sudo rsnapshot -t daily

# Run an interval by hand
sudo rsnapshot daily
```
