# ansible-role-torrent

Provision an [rtorrent](https://github.com/rakshasa/rtorrent) instance on a remote host and install companion
scripts on the controller.

- **Remote host:** rtorrent as a `Type=forking` systemd service inside a tmux session on a private socket, so it
  never shares a server with your own tmux sessions.
- **Controller:** cron jobs to upload `.torrent` files, sync completed downloads back, and extract archives.

## Usage

```bash
make torrent

# Attach to the rtorrent UI on the remote host
tmux -L rtorrent attach -t rtorrent
```

The play targets the `torrent` group (the remote rtorrent host). [tasks/localhost.yml](./tasks/localhost.yml) is
delegated to the implicit `localhost` (the controller) and runs only when the target is not localhost.

- A delegated task resolves plain variables from the play host, not the delegate, so the controller-side
  `torrent_local_*` vars live in the play host's `host_vars/`, not a `localhost` host_vars file.
- Do not add `localhost` to the inventory: it would be swept into every `hosts: all` play.

## Scripts

Installed to `/usr/local/bin/` on the controller:

| Script | Purpose |
| --- | --- |
| [`mvt`](./templates/mvt) | Upload `*.torrent` files from local watch directories to the remote watch directory via scp |
| [`synct`](./templates/synct) | Rsync completed downloads from every remote torrent host to the local incoming directory |
| [`unrart`](./templates/unrart) | Extract archives (rar, zip, tar.gz, tar.bz2) in a directory up to 5 levels deep |
| [`orgt`](./templates/orgt) | Ask Claude to organize incoming entries into the media libraries; skips entries still present on a remote (synct would re-download them). Run manually; not on cron |

### Shared behaviour

- Each script is generated with one call per host in the `torrent` group, each built from that host's own
  `hostvars[host].torrent_root_directory` (falling back to the play host's value). The role's
  `torrent_watch_directory` and `torrent_completed_directory` cannot be used here: a delegated task resolves
  plain variables from the play host, so they would name one host's paths for every host, and which host that is
  would depend on render order. The scripts append the `watch/` and `completed/` subdirectory names instead.
- `mvt`, `synct` and `unrart` keep going when one host, file or archive fails, and report at the end with a
  non-zero exit so cron notices.
- `--quiet` suppresses progress output only. `warn()` and `error()` print regardless, because the cron jobs always
  pass `--quiet` and a suppressed warning would leave the closing error with nothing naming what failed. A healthy
  quiet run prints nothing, so anything in the log is worth reading.
- `mvt` and `synct` each take a `flock` (`mvt` one for the whole run, `synct` one per host and directory) and fail
  when it is already held. A transfer takes seconds and cron fires every 2 minutes, so a held lock means a prior
  run is wedged, not that runs legitimately overlap.
- Both pass ssh `ConnectTimeout=10` with `ServerAliveInterval=15`/`ServerAliveCountMax=4` to bound how long that
  lock can be held. Without them an unreachable host waits out the kernel's TCP connect timeout, which is longer
  than the cron interval, and a transfer that stalls after connecting hangs until `TCPKeepAlive` gives up roughly
  two hours later.

### mvt

- A `.torrent` modified in the last 30 seconds is left for the next run: a client may still be writing it, and a
  successful `scp` deletes the local copy, so a truncated upload would be unrecoverable.
- A failed upload keeps the file, warns, lets the remaining files and watch directories proceed, and exits
  non-zero so cron reports the run.
- A successful upload deletes the local file, so with more than one torrent host a `.torrent` goes to the first
  host that accepts it, not to all of them.
- One `flock` covers the whole run, because two overlapping runs would race to `rm` the same file. Each file is
  passed to `scp` as `./name`, because a name beginning with a dash is otherwise read as an option.

### orgt

`claude -p` buffers its text output, so it prints nothing until the run ends and a large batch takes tens of
minutes. Every run streams instead, via `--output-format stream-json` (which `-p` only permits alongside
`--verbose`) piped through `jq`, one line per tool call. `jq` is a hard dependency, checked up front. Two
properties of that filter are load-bearing, because the pipe consumes Claude's stdout:

- The `result` event prints unclipped, keeping its line breaks. It is the only full copy of the run's report,
  including deferred entries. Tool calls and narration collapse to one clipped line; a `Bash` line shows the
  command rather than its description, naming the paths being moved.
- Lines that are not JSON objects are dropped (`-R` plus `fromjson`). `jq` exiting on one would `SIGPIPE` Claude
  mid-batch, possibly between a move and its post-verify count.

Prompt and safety:

- The media-root guides require up-front sign-off for a batch over 10 items or spanning libraries, which nobody
  can give under `-p`: an unanswered question ends the run having moved nothing. The prompt states that invoking
  the script is that sign-off for exactly the listed entries, keeps every other safety rule (per-pass dry-run,
  collision detection, non-overwriting moves, post-verify counts, `HISTORY.md`), and defers anything it would
  otherwise ask about instead of guessing. A deferred entry stays in the incoming directory and is reported at the
  end.
- Preview with `--dry-run`, which prints its list even under `--quiet`, since that list is the only thing it
  produces.
- The entry list is fenced between `BEGIN ENTRIES`/`END ENTRIES` markers and labelled as data the run must not act
  on. A release name is chosen by whoever packaged the download and this run has every permission check disabled,
  so a name that reads like an instruction has to be handled as part of the name. The dash-space prefix on each
  line is load-bearing for the same reason: it keeps a name from reproducing the end marker. Names containing a
  newline are skipped earlier, before the list is built.
- `claude` runs from the library root, not the incoming directory: every destination is a sibling of `incoming/`,
  so the root is the smallest cwd covering them all without an `--add-dir` grant, and sessions bucket by cwd. A
  resume must run from that same directory, so the first streamed line prints the full `cd ... && claude --resume
  ...` command.

### unrart

- A failed archive does not stop the batch. Nothing removes a corrupt or truncated archive from the incoming
  directory, so aborting on one would block every archive sorting after it, on that run and every run after it.
  Each failure warns with the extractor's exit code, and the run ends non-zero.
- `unrar` exit 10 is a warning rather than a failure: a file the archive contains is already on disk.
- A pass that finds no archives says so only when not quiet. Most completed downloads contain no archive, so under
  cron that is the usual outcome, and the log it appends to is not rotated.
- Only the first volume of a multi-volume RAR set is extracted; `unrar` follows the chain from there. Old-style
  `.r00`/`.r01` volumes do not match the search expression, but every part of a `name.partN.rar` set does, so the
  later parts are filtered by volume number. `part1`, `part01` and `part001` are all first volumes, and the number
  is compared as base 10 so `part08` is not read as octal.
- The search matches files only. A directory named like an archive would otherwise be handed to an extractor, and
  `--delete-archives` would then try to `rm -f` a directory and fail.

## Cron jobs

Installed to `/etc/cron.d/ansible-role-torrent` on the controller:

| Job | Schedule |
| --- | --- |
| `mvt` | Every 2 minutes |
| `synct` (then `unrart` on success) | Every 2 minutes |

## Variables

See [defaults/main.yml](./defaults/main.yml), which comments the non-obvious ones. Both the remote-host overrides
and the controller-side `torrent_local_*` overrides go in the play host's `host_vars/`.

| Variable | Description |
| --- | --- |
| `torrent_user` | Account rtorrent runs as, and whose home holds `.rtorrent.rc` |
| `torrent_root_directory` | Base directory for all torrent data on the remote host |
| `torrent_download_rate_kib`, `torrent_upload_rate_kib` | Rate limits in KiB/s; 0 is unlimited |
| `torrent_pieces_memory_max` | Address space rtorrent maps piece data into. File-backed page cache, so it need not fit in RAM; libtorrent rejects anything below 512M |
| `torrent_port_range` | rtorrent peer port range. The top of the range is reused as `torrent_dht_port` |
| `torrent_tmux_socket` | Private tmux socket, so the service and your own sessions do not share a server |
| `torrent_local_user` | Controller account that owns the cron jobs |
| `torrent_local_incoming_directory` | Controller directory for synced downloads. Required |
| `torrent_local_watch_directories` | Controller directories to watch for `.torrent` files. Required |
| `torrent_local_synct_log_file` | File the `synct` cron job appends its output to. Not rotated; `--quiet` reaches rsync, so it holds no progress output |

## CI

The templated scripts (`mvt`, `orgt`, `synct`, `unrart`) are ShellCheck'd in
[.github/workflows/lint.yml](../../.github/workflows/lint.yml). The `shellcheck` job discovers every shell script
under `roles/` by shebang; scripts under `templates/` are rendered first (Jinja2 expressions to placeholders),
scripts under `files/` are linted as-is. Suppress findings with `# shellcheck disable=...` comments in the
templates.

That render is a `sed` approximation, not a Jinja2 parse, so a template Jinja2 cannot render still passes CI. Bash
that opens a Jinja tag is the trap: `${#var}` starts a comment and breaks the render at play time.
