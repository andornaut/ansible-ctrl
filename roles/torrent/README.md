# ansible-role-torrent

Provision an [rtorrent](https://github.com/rakshasa/rtorrent) instance on a remote host and install companion
scripts on the controller.

The remote host runs rtorrent as a `Type=forking` systemd service inside a tmux session on a private socket, so
it never shares a server with your own tmux sessions. The controller runs cron jobs to upload `.torrent` files,
sync completed downloads back, and extract archives.

## Usage

```bash
make torrent
```

The play targets the `torrent` group (the remote rtorrent host). The tasks in [tasks/localhost.yml](./tasks/localhost.yml)
are delegated to the implicit `localhost` (the controller) and run only when the target is not localhost, installing
the `mvt`, `synct`, and `unrart` scripts plus their cron jobs. A delegated task resolves plain variables from the
play host, not the delegate, so the controller-side `torrent_local_*` vars live in the play host's `host_vars/`
(e.g. `host_vars/prime.yml`), not a `localhost` host_vars file. Do not add `localhost` to the inventory: it would
be swept into every `hosts: all` play.

Attach to the rtorrent UI with:

```bash
tmux -L rtorrent attach -t rtorrent
```

## Scripts

Installed to `/usr/local/bin/` on the controller:

| Script | Purpose |
| --- | --- |
| [`mvt`](./templates/mvt) | Upload `*.torrent` files from local watch directories to the remote watch directory via scp |
| [`synct`](./templates/synct) | Rsync completed downloads from every remote torrent host to the local incoming directory; skips overlapping runs |
| [`unrart`](./templates/unrart) | Extract archives (rar, zip, tar.gz, tar.bz2) in a directory up to 5 levels deep |

## Cron jobs

Installed to `/etc/cron.d/ansible-role-torrent` on the controller:

| Job | Schedule |
| --- | --- |
| `mvt` | Every 2 minutes |
| `synct` (then `unrart` on success) | Every 2 minutes |

## Variables

See [defaults/main.yml](./defaults/main.yml). Both remote-host overrides (rate limits, directories) and the
controller-side `torrent_local_*` overrides go in the play host's `host_vars/` (e.g. `host_vars/prime.yml`);
the delegated tasks resolve plain variables from the play host, so a `localhost` host_vars file is never read.

| Variable | Default | Description |
| --- | --- | --- |
| `torrent_root_directory` | `~/torrents` | Base directory for all torrent data on the remote host |
| `torrent_download_rate_kib` | `0` (unlimited) | Download rate limit in KiB/s |
| `torrent_upload_rate_kib` | `0` (unlimited) | Upload rate limit in KiB/s |
| `torrent_port_range` | `20000-20999` | rtorrent peer port range; the top of the range is reused as the DHT UDP port |
| `torrent_local_incoming_directory` | (required) | Controller directory for synced downloads |
| `torrent_local_watch_directories` | (required) | Controller directories to watch for `.torrent` files |
| `torrent_local_synct_log_file` | `/tmp/synct.log` | File the `synct` cron job appends its output to (not rotated) |

## CI

The templated scripts (`mvt`, `synct`, `unrart`) are ShellCheck'd in [.github/workflows/lint.yml](../../.github/workflows/lint.yml):
the workflow renders the Jinja2 expressions to placeholders, then runs ShellCheck on the results. Suppress
findings with `# shellcheck disable=...` comments in the templates.
