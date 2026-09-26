# ansible-role-torrent

Installs [rtorrent](https://github.com/rakshasa/rtorrent) on the `torrent` hosts, and its transfer scripts and cron
jobs on the controller.

## Usage

```bash
make torrent

# The controller's scripts and cron jobs on their own
make torrent -- --limit faramir_controller
```

[torrent.yml](../../torrent.yml) applies the role to the `torrent` group, then
[tasks/controller.yml](./tasks/controller.yml) to `faramir_controller`. No tags: select a half with `--limit`.

## Variables

See [defaults/main.yml](./defaults/main.yml).

| Variable                                               | Purpose                                                                                     |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------- |
| `torrent_user`, `torrent_group`                        | Account rtorrent runs as, and the group owning its directories (defaults to `torrent_user`) |
| `torrent_root_directory`                               | Base directory for all torrent data. Required in each torrent host's `host_vars`            |
| `torrent_incoming_directory`                           | Where rtorrent downloads to                                                                 |
| `torrent_session_directory`                            | rtorrent's session directory                                                                |
| `torrent_download_rate_kib`, `torrent_upload_rate_kib` | Rate limits in KiB/s; 0 is unlimited                                                        |
| `torrent_pieces_memory_max`                            | Address space for piece data. Page cache, so it need not fit in RAM; minimum 512M           |
| `torrent_port_range`                                   | Peer port range. The top of the range is also the DHT port                                  |
| `torrent_local_user`                                   | Controller account that owns the cron jobs                                                  |
| `torrent_local_incoming_directory`                     | Controller directory for synced downloads. Required                                         |
| `torrent_local_watch_directories`                      | Controller directories to watch for `.torrent` files. Required                              |
| `torrent_local_synct_log_file`                         | Log of the `synct` cron job. Not rotated                                                    |

## Installed files

On the `torrent` hosts:

| Path                                   | Purpose                                                                                                   |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `~/.rtorrent.rc`                       | rtorrent configuration, in `torrent_user`'s home                                                          |
| `/etc/systemd/system/rtorrent.service` | rtorrent in a tmux session on a private socket. Sandboxed: no sudo, and read-only outside its directories |

On the controller:

| Path                                          | Purpose                                                                                                                    |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| [`/usr/local/bin/mvt`](./templates/mvt)       | Upload `*.torrent` files from the local watch directories to a torrent host's watch directory                              |
| [`/usr/local/bin/synct`](./templates/synct)   | Rsync completed downloads from every torrent host to the local incoming directory                                          |
| [`/usr/local/bin/unrart`](./templates/unrart) | Extract rar and zip archives in a directory, never overwriting a file                                                      |
| [`/usr/local/bin/orgt`](./templates/orgt)     | Ask Claude to organize incoming entries into the media libraries. Run by hand; entries still on a torrent host are skipped |
| `/etc/cron.d/ansible-role-torrent`            | `mvt` every 2 minutes; `synct` every 2 minutes, then `unrart` on success                                                   |

## Scripts

| Constraint                         | Detail                                                                                                                                                        |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Failures do not stop a run         | `mvt`, `synct` and `unrart` warn, carry on past a failed host, file or archive, and exit non-zero at the end                                                  |
| A quiet run's log shows failures   | `--quiet` suppresses progress only, so anything in the cron log names something that failed                                                                   |
| A held lock means a stuck run      | `mvt` and `synct` fail when a prior run still holds their `flock`                                                                                             |
| `mvt` deletes what it uploads      | A `.torrent` goes to the first torrent host that accepts it. Files modified in the last 30 seconds wait for the next run                                      |
| `unrart` extracts rar and zip only | Other formats would be decompressed again on every pass. Only the first volume of a multi-volume RAR set is passed to `unrar`                                 |
| `orgt` signs off the batch         | Running it approves exactly the listed entries. Anything it would otherwise ask about stays in the incoming directory and is reported. `--dry-run` lists them |

## Notes

| Constraint                        | Detail                                                                                                                                                            |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Scripts cover the whole group     | They name every torrent host, but only a run reaching the controller rewrites them. After adding a torrent host, run `make torrent -- --limit faramir_controller` |
| `torrent_root_directory` per host | The controller play refuses a torrent host that does not set it                                                                                                   |
| Templates are ShellChecked        | [tests/lint.sh](../../tests/lint.sh) renders Jinja2 to placeholders with `sed`, so a template Jinja2 cannot render still passes. `${#var}` breaks the render      |

## Operations

```bash
# Attach to the rtorrent UI on a torrent host
tmux -L rtorrent attach -t rtorrent
```
