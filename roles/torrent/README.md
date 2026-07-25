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

**Progress output.** `orgt` invokes `claude -p`, which prints nothing until the whole run ends, and a large batch
can take tens of minutes. Run it with `--verbose` to see progress: that switches the invocation to
`--output-format stream-json` (which `-p` only permits alongside `--verbose`) and pipes the events through `jq`,
printing the session id and then one timestamped line per tool call plus Claude's narration. `--verbose` requires
`jq`; the script checks for it up front. Two properties of that filter are load-bearing, because the pipe
consumes Claude's stdout and anything the filter drops is gone:

- The `result` event prints unclipped, keeping its own line breaks. It is the only complete copy of the run's
  report, including which entries were deferred. Mid-run tool calls and narration are collapsed to one line and
  clipped, being progress rather than the deliverable; for a `Bash` call the line shows the command (the paths it
  moves) rather than its one-line description.
- Lines that are not parseable JSON objects are dropped rather than parsed. `jq` exiting non-zero on one would
  `SIGPIPE` Claude mid-batch, possibly between a move and its post-verify count.

**Non-interactive contract.** The library guides under the media root require up-front sign-off before a batch
that touches more than 10 items or spans more than one library, which no one can give inside `claude -p`: an
unanswered question ends the run with nothing moved. The prompt therefore states that invoking the script *is*
that sign-off, for exactly the entries listed in the run, and leaves every other safety rule (per-pass dry-run,
collision detection, non-overwriting moves, post-verify counts, `HISTORY.md`) untouched. Anything that would
otherwise stop and ask is deferred rather than guessed: that entry stays in the incoming directory and is
reported at the end with the question that would have been asked. Preview the batch with `--dry-run` before
committing to it.

**Working directory.** The `claude` invocation runs from the library root (the incoming directory's parent), not
from the incoming directory. Every destination library is a sibling of `incoming/`, so the root is the smallest
cwd that covers them all without an `--add-dir` grant, and because sessions are bucketed by cwd, every run lands
in the same place for `claude --resume`. A resume has to happen from that same directory, so the `--verbose`
session line prints the `cd ... && claude --resume ...` command in full.

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
