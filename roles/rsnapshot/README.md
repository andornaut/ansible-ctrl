# ansible-role-rsnapshot

Provisions [rsnapshot](https://rsnapshot.org/) for automated incremental backups.

## Usage

```bash
make rsnapshot
```

## Variables

See [defaults/main.yml](./defaults/main.yml).

| Variable                         | Purpose                                                                                 |
| -------------------------------- | --------------------------------------------------------------------------------------- |
| `rsnapshot_hosts`                | Hosts, directories, and backup scripts to snapshot. Required                            |
| `rsnapshot_directory`            | Snapshot root                                                                           |
| `rsnapshot_preexec_script`       | Where the mountpoint check is installed                                                 |
| `rsnapshot_required_mountpoints` | Mountpoints checked before the lowest interval. Empty installs no check                 |
| `rsnapshot_retention`            | Snapshots kept per interval. A null value omits both the `retain` line and the cron job |
| `rsnapshot_schedule`             | Cron time per interval, keyed to match `rsnapshot_retention`                            |

Each entry in `rsnapshot_hosts` takes `name`, `host`, and at least one of `directories` (trailing
slash required by rsnapshot) or `scripts`, plus one optional key:

| Key    | Purpose                                                                                                                                                                                           |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `name` | The address rsync dials and the directory the snapshot lands in. Required                                                                                                                         |
| `host` | Inventory name of the host, which `name` is not. Required, and asserted to be in the inventory: it decides the login account, whether the point is read locally, and whether that login escalates |
| `user` | Login account, overriding the `ansible_user` of `host`, which is otherwise used and then `primary_user`                                                                                           |

Locality and escalation are derived, not declared:

| Condition                           | Effect                                                                                                                          |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `host` is the host running the role | Read from the local filesystem, with no login prefix and no escalation                                                          |
| Login account is `root`             | Pulled over SSH with no escalation: the point restates `rsync_long_args` without the sudo wrapper. pfSense has no `sudo` at all |
| Any other login account             | Pulled over SSH, escalating through the global `rsync_long_args`, which carries `--rsync-path='sudo /usr/bin/rsync'`            |

A path naming an account belongs to the host being backed up, not the one running the role, so it
resolves through `hostvars`, which templates in the owning host's scope. A bare `{{ primary_user }}`
resolves in the scope of the host rsnapshot runs on and is only correct where the two agree. Role
defaults are not inventory data and so are absent from `hostvars`: a host taking `{role}_user`'s
default rather than declaring it has only `primary_user` to name.

A directory may be a mapping of `path` and `exclude` rather than a plain path, which adds one
`exclude=` per pattern to that backup point. `--delete-excluded` is in force, so a pattern added
later also drops what earlier runs stored.

```yaml
rsnapshot_hosts:
  - name: example.com
    host: example
    directories:
      - /etc/
      - "/home/{{ hostvars['example'].primary_user }}/.ssh/"
      - "/home/{{ hostvars['example'].desktop_user }}/.gnupg/"
      - path: /var/docker-volumes/
        exclude:
          - cache/
    scripts:
      - command: /usr/local/bin/backupdockerpostgresql
        args: --host root@example.com --container postgresql postgresql.gz

  - name: router.example.com
    host: router-example
    directories:
      - /conf/config.xml

rsnapshot_required_mountpoints:
  - /media/nas

rsnapshot_retention:
  hourly:
  daily: 7
  weekly: 4
  monthly: 12
```

## Notes

- Cron runs one job per retention interval as root.
- Hosts are pulled over SSH; the entry naming the host the role runs on is read from the local filesystem.
- `backupmysql` and `backupdockerpostgresql` are installed to `/usr/local/bin` for use as `scripts`.
- Snapshots land under `rsnapshot_directory` as `{interval}.{n}/` (`.0` is newest): directories in `{name}/`,
  script output in `{name}_{script}/`.
- Unchanged files are hard-linked between snapshots, so `du` over the whole root overstates disk usage.
  A file rewritten between runs is stored in full each time, so a large database costs its own size per
  retained snapshot.
- `rsnapshot_required_mountpoints` installs a `cmd_preexec` check, which rsnapshot runs for the lowest
  configured interval only. That is also the only interval reading sources, the higher ones rotating what
  is already stored, so a missing filesystem cannot replace the newest snapshot with nothing.
- An `exclude` pattern is emitted quoted, so one containing a space works. Patterns containing a double
  quote do not: rsnapshot permits no nested quoting.
- The cron runs as root, so a remote point authenticates with root's key on the host running the role,
  not the operator's. That key has to be authorized for the account `user` names on the target, which for
  a point taking `user: root` is the target's root login. Nothing in this role distributes it, and an
  unauthorized key fails only at the next cron run, as `rsync returned 255` with `Permission denied
(publickey)` in `/var/log/rsnapshot.log`.
- On a pfSense target the key belongs in `authorized_keys2`. `authorized_keys` is regenerated from
  `config.xml` on boot and on every user save, which drops anything written to it directly; `sshd -T`
  reports both files under `authorizedkeysfile`.

## Operations

```bash
# Validate /etc/rsnapshot.conf, also run as a handler after a configuration change
sudo rsnapshot configtest

# Show the rsync commands an interval would run, without running them
sudo rsnapshot -t daily

# Run an interval by hand
sudo rsnapshot daily
```
