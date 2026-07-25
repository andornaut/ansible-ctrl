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
the scripts and cron jobs below. A delegated task resolves plain variables from the
play host, not the delegate, so the controller-side `torrent_local_*` vars live in the play host's `host_vars/`
(e.g. `host_vars/torrentbox.yml`), not a `localhost` host_vars file. Do not add `localhost` to the inventory: it would
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
| [`orgt`](./templates/orgt) | Ask Claude to organize incoming entries into the media libraries; skips entries still present on a remote (synct would re-download them). Run manually; not on cron. |

### orgt

`claude -p` buffers its text output, so a run prints nothing until it ends, and a large batch takes tens of
minutes. `--verbose` streams instead: `--output-format stream-json` (which `-p` only permits alongside
`--verbose`) piped through `jq`, one line per tool call. It requires `jq`, checked up front. Two properties of
that filter are load-bearing, because the pipe consumes Claude's stdout:

- The `result` event prints unclipped, keeping its line breaks. It is the only full copy of the run's report,
  including deferred entries. Tool calls and narration collapse to one clipped line; a `Bash` line shows the
  command rather than its description, naming the paths being moved.
- Lines that are not JSON objects are dropped. `jq` exiting on one would `SIGPIPE` Claude mid-batch, possibly
  between a move and its post-verify count.

The media-root guides require up-front sign-off for a batch over 10 items or spanning libraries, which nobody can
give under `-p`: an unanswered question ends the run having moved nothing. The prompt states that invoking the
script is that sign-off for exactly the listed entries, keeps every other safety rule (per-pass dry-run, collision
detection, non-overwriting moves, post-verify counts, `HISTORY.md`), and defers anything it would otherwise ask
about instead of guessing: that entry stays in the incoming directory and is reported at the end. Preview with
`--dry-run`.

`claude` runs from the library root, not the incoming directory. Every destination is a sibling of `incoming/`, so
the root is the smallest cwd covering them all without an `--add-dir` grant, and sessions bucket by cwd. A resume
must run from that same directory, so `--verbose` prints the full `cd ... && claude --resume ...` command.

## Cron jobs

Installed to `/etc/cron.d/ansible-role-torrent` on the controller:

| Job | Schedule |
| --- | --- |
| `mvt` | Every 2 minutes |
| `synct` (then `unrart` on success) | Every 2 minutes |

## Variables

See [defaults/main.yml](./defaults/main.yml). Both the remote-host overrides (rate limits, directories) and the
controller-side `torrent_local_*` overrides go in the play host's `host_vars/` (e.g. `host_vars/torrentbox.yml`).

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

The templated scripts (`mvt`, `orgt`, `synct`, `unrart`) are ShellCheck'd in [.github/workflows/lint.yml](../../.github/workflows/lint.yml).
The `shellcheck` job discovers every shell script under `roles/` by shebang, so these are covered along with the
other roles' scripts. Scripts under `templates/` are rendered first (Jinja2 expressions to placeholders); scripts
under `files/` are linted as-is. Suppress findings with `# shellcheck disable=...` comments in the templates.

That render is a `sed` approximation, not a Jinja2 parse, so a template Jinja2 cannot render still passes CI. Bash
that opens a Jinja tag is the trap: `${#var}` starts a comment, breaking the render at play time.
