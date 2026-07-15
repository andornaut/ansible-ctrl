# ansible-role-rsnapshot

Provisions [rsnapshot](http://rsnapshot.org/) for automated incremental backups.

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
| `rsnapshot_retention` | Snapshots kept per interval. A null value omits both the `retain` line and the cron job |
| `rsnapshot_sudo` | Run the remote rsync via `sudo`, for directories the SSH user cannot read |

Each entry in `rsnapshot_hosts` takes a `name`, an optional `local` and `user`, a list of `directories` (trailing
slash required by rsnapshot), and a list of `scripts`.

```yaml
rsnapshot_hosts:
  - name: example.com
    user: root
    directories:
      - /etc/
      - /var/docker-volumes/
    scripts:
      - command: /usr/local/bin/backupdockerpostgresql
        args: --host root@example.com --container postgresql postgresql.gz

rsnapshot_retention:
  hourly:
  daily: 7
  weekly: 4
  monthly: 12
```

## Notes

- Cron runs one job per retention interval as root.
- Remote hosts are pulled over SSH; hosts marked `local: true` or named `localhost` are read from the local
  filesystem.
- `backupmysql` and `backupdockerpostgresql` are installed to `/usr/local/bin` for use as `scripts`.
- Snapshots land under `rsnapshot_directory` as `{interval}.{n}/` (`.0` is newest): directories in `{host}/`,
  script output in `{host}_{script}/`.
- Unchanged files are hard-linked between snapshots, so `du` over the whole root overstates disk usage.

## Operations

```bash
# Validate /etc/rsnapshot.conf, also run as a handler after every change
sudo rsnapshot configtest

# Show the rsync commands an interval would run, without running them
sudo rsnapshot -t daily

# Run an interval by hand
sudo rsnapshot daily
```
