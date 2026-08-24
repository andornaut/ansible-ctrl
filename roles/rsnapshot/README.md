# ansible-role-rsnapshot

Provisions [rsnapshot](https://rsnapshot.org/) for automated incremental backups.

## Usage

```bash
make rsnapshot
```

## Variables

See [defaults/main.yml](./defaults/main.yml).

| Variable | Purpose |
| --- | --- |
| `rsnapshot_hosts` | Hosts, directories, and backup scripts to snapshot. Required |
| `rsnapshot_directory` | Snapshot root |
| `rsnapshot_preexec_script` | Where the mountpoint check is installed |
| `rsnapshot_required_mountpoints` | Mountpoints checked before the lowest interval. Empty installs no check |
| `rsnapshot_retention` | Snapshots kept per interval. A null value omits both the `retain` line and the cron job |
| `rsnapshot_schedule` | Cron time per interval, keyed to match `rsnapshot_retention` |
| `rsnapshot_sudo` | Run the remote rsync via `sudo`, for directories the SSH user cannot read |

Each entry in `rsnapshot_hosts` takes a `name` and at least one of `directories` (trailing slash
required by rsnapshot) or `scripts`, plus these optional keys:

| Key | Purpose |
| --- | --- |
| `host` | Inventory name of the host, which `name` is not: that one is the address rsync dials and the snapshot directory. Supplies the login default. The role asserts the name is in the inventory: `hostvars` answers for one outside it with nothing rather than an error, which the login default would take for an omitted key |
| `local` | Read from the local filesystem instead of pulling over SSH |
| `user` | Login account, defaulting to the `ansible_user` of `host` and then to `primary_user`: the account the fleet authorizes and the one `rsnapshot_sudo` escalates from |
| `sudo` | Override `rsnapshot_sudo` for this host. A host logging in already privileged sets `false` |

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
    user: root
    sudo: false
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
- Remote hosts are pulled over SSH; hosts marked `local: true` are read from the local filesystem.
- `backupmysql` and `backupdockerpostgresql` are installed to `/usr/local/bin` for use as `scripts`.
- Snapshots land under `rsnapshot_directory` as `{interval}.{n}/` (`.0` is newest): directories in `{host}/`,
  script output in `{host}_{script}/`.
- Unchanged files are hard-linked between snapshots, so `du` over the whole root overstates disk usage.
  A file rewritten between runs is stored in full each time, so a large database costs its own size per
  retained snapshot.
- `rsnapshot_required_mountpoints` installs a `cmd_preexec` check, which rsnapshot runs for the lowest
  configured interval only. That is also the only interval reading sources, the higher ones rotating what
  is already stored, so a missing filesystem cannot replace the newest snapshot with nothing.
- An `exclude` pattern is emitted quoted, so one containing a space works. Patterns containing a double
  quote do not: rsnapshot permits no nested quoting.

## Operations

```bash
# Validate /etc/rsnapshot.conf, also run as a handler after a configuration change
sudo rsnapshot configtest

# Show the rsync commands an interval would run, without running them
sudo rsnapshot -t daily

# Run an interval by hand
sudo rsnapshot daily
```
