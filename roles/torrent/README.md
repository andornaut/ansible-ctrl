# ansible-role-torrent

Installs [rtorrent](https://github.com/rakshasa/rtorrent) on the `torrent` hosts, and its transfer scripts and cron
jobs on the controller.

## Usage

```bash
make torrent

# The controller's scripts and cron jobs on their own
make torrent -- --limit faramir_controller
```

[torrent.yml](../../torrent.yml) has two plays. The first applies this role to the `torrent` group; the second
imports [tasks/controller.yml](./tasks/controller.yml) against `faramir_controller` with `tasks_from`, so
`--limit faramir_controller` applies the controller's scripts and cron jobs without the rtorrent half.

## Tags

No tags. Select a half with `--limit`.

## Variables

See [defaults/main.yml](./defaults/main.yml), which comments the non-obvious ones.

| Variable                                               | Purpose                                                                                                                                |
| ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| `torrent_user`                                         | Account rtorrent runs as, and whose home holds `.rtorrent.rc`                                                                          |
| `torrent_group`                                        | Group owning the torrent directories and `.rtorrent.rc`, and the service's `Group=`. Defaults to `torrent_user`                        |
| `torrent_root_directory`                               | Base directory for all torrent data on the remote host. Required in each torrent host's `host_vars`                                    |
| `torrent_incoming_directory`                           | Where rtorrent downloads to, under `torrent_root_directory`                                                                            |
| `torrent_session_directory`                            | rtorrent's session directory, holding its lock and the service's PID file, under `torrent_root_directory`                              |
| `torrent_download_rate_kib`, `torrent_upload_rate_kib` | Rate limits in KiB/s; 0 is unlimited                                                                                                   |
| `torrent_pieces_memory_max`                            | Address space rtorrent maps piece data into. File-backed page cache, so it need not fit in RAM; libtorrent rejects anything below 512M |
| `torrent_port_range`                                   | rtorrent peer port range. The top of the range is reused as `torrent_dht_port`                                                         |
| `torrent_tmux_socket`                                  | Private tmux socket, so the service and your own sessions do not share a server                                                        |
| `torrent_local_user`                                   | Controller account that owns the cron jobs                                                                                             |
| `torrent_local_incoming_directory`                     | Controller directory for synced downloads. Required                                                                                    |
| `torrent_local_watch_directories`                      | Controller directories to watch for `.torrent` files. Required                                                                         |
| `torrent_local_synct_log_file`                         | File the `synct` cron job appends its output to. Not rotated; `--quiet` reaches rsync, so it holds no progress output                  |

## Installed files

On the `torrent` hosts:

| Path                                   | Purpose                                                                                                                                                                                         |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `~/.rtorrent.rc`                       | rtorrent configuration, in `torrent_user`'s home                                                                                                                                                |
| `/etc/systemd/system/rtorrent.service` | rtorrent as a `Type=forking` service inside a tmux session on a private socket. Sandboxed: `NoNewPrivileges` (no sudo), and the filesystem read-only but for the torrent directories and `/tmp` |

On the controller:

| Path                                          | Purpose                                                                                                                                                             |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`/usr/local/bin/mvt`](./templates/mvt)       | Upload `*.torrent` files from local watch directories to the remote watch directory via scp                                                                         |
| [`/usr/local/bin/synct`](./templates/synct)   | Rsync completed downloads from every remote torrent host to the local incoming directory                                                                            |
| [`/usr/local/bin/unrart`](./templates/unrart) | Extract archives (rar, zip, tar.gz, tar.bz2) in a directory up to 5 levels deep                                                                                     |
| [`/usr/local/bin/orgt`](./templates/orgt)     | Ask Claude to organize incoming entries into the media libraries; skips entries still present on a remote (synct would re-download them). Run manually; not on cron |
| `/etc/cron.d/ansible-role-torrent`            | `mvt` every 2 minutes; `synct` every 2 minutes, then `unrart` on success                                                                                            |

## Scripts

| Constraint                                                                                                                                                                                       | Detail                                                                                                                                                                                     |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Each script is generated with one call per host in `groups['torrent']`, from that host's own `hostvars[host].torrent_root_directory`, appending the `watch/` and `completed/` subdirectory names | The role's `torrent_watch_directory` and `torrent_completed_directory` would name one host's paths for every host                                                                          |
| `mvt`, `synct` and `unrart` keep going past a failed host, file or archive, and exit non-zero at the end                                                                                         | cron notices the exit code, not the warnings                                                                                                                                               |
| `--quiet` suppresses progress output only; `warn()` and `error()` print regardless                                                                                                               | A healthy quiet run prints nothing, so anything in the log names something that failed                                                                                                     |
| `mvt` and `synct` take a `flock` (`mvt` one for the whole run, `synct` one per host and directory) and fail when it is held                                                                      | A transfer takes seconds and cron fires every 2 minutes, so a held lock means a prior run is stuck                                                                                         |
| Both pass ssh `ConnectTimeout=10`, `ServerAliveInterval=15`, `ServerAliveCountMax=4`                                                                                                             | Bounds how long that lock is held. Otherwise an unreachable host waits out the kernel's TCP connect timeout, and a stalled transfer hangs until `TCPKeepAlive` gives up, roughly two hours |

## mvt

| Constraint                                                            | Detail                                                                                                  |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| A `.torrent` modified in the last 30 seconds is left for the next run | A client may still be writing it, and a successful `scp` deletes the local copy                         |
| A successful upload deletes the local file                            | With more than one torrent host a `.torrent` goes to the first host that accepts it, not to all of them |
| A failed upload keeps the file, warns, and proceeds                   | The run still exits non-zero                                                                            |
| One `flock` covers the whole run                                      | Two overlapping runs would race to `rm` the same file                                                   |
| Each file is passed to `scp` as `./name`                              | A name beginning with a dash is otherwise read as an option                                             |

## orgt

`claude -p` buffers its text output, so a large batch prints nothing for tens of minutes. Every run streams
instead, via `--output-format stream-json` (which `-p` only permits alongside `--verbose`) piped through `jq`,
one line per tool call. `jq` is a hard dependency, checked up front.

| Constraint                                                                                                                                      | Detail                                                                                                                                                                                                                                                                                                                                                     |
| ----------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| The `result` event prints unclipped, keeping its line breaks                                                                                    | The pipe consumes Claude's stdout, and this event is the only full copy of the run's report, deferred entries included. Tool calls and narration collapse to one clipped line; a `Bash` line shows the command, not its description                                                                                                                        |
| Lines that are not JSON objects are dropped (`-R` plus `fromjson`)                                                                              | `jq` exiting on one would `SIGPIPE` Claude mid-batch, possibly between a move and its post-verify count                                                                                                                                                                                                                                                    |
| Invoking the script is the up-front sign-off, for exactly the listed entries                                                                    | The media-root guides require sign-off for a multi-item, multi-library batch, which nobody can give under `-p`. Every other safety rule stands (per-pass dry-run, collision detection, non-overwriting moves, post-verify counts, `HISTORY.md`), and anything the run would otherwise ask about stays in the incoming directory and is reported at the end |
| The entry list is fenced between `BEGIN ENTRIES`/`END ENTRIES` and labelled as data the run must not act on, each line prefixed with dash-space | This run has every permission check disabled, so a release name that reads like an instruction must stay part of the name and must not be able to reproduce the end marker. Names containing a newline are skipped                                                                                                                                         |
| `claude` runs from the library root, not the incoming directory                                                                                 | Every destination is a sibling of `incoming/`, so the root is the smallest cwd covering them all without an `--add-dir` grant. Sessions are grouped by cwd, so the first streamed line prints the full `cd ... && claude --resume ...` command                                                                                                             |
| `--dry-run` prints its list even under `--quiet`                                                                                                | That list is the only thing the run produces                                                                                                                                                                                                                                                                                                               |

## unrart

| Constraint                                                                        | Detail                                                                                                                                                                                                                                                                                                                   |
| --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| A failed archive warns with the extractor's exit code and does not stop the batch | Nothing removes a corrupt archive from the incoming directory, so aborting on one would block every archive after it, on every run                                                                                                                                                                                       |
| A file already on disk is never overwritten                                       | `unrar -o-`, `tar --skip-old-files` and `unzip -n` each skip it                                                                                                                                                                                                                                                          |
| `unrar` exit 10 is a warning, not a failure                                       | A file the archive contains is already on disk                                                                                                                                                                                                                                                                           |
| A pass that finds no archives says so only when not quiet                         | The usual outcome under cron, whose log is not rotated                                                                                                                                                                                                                                                                   |
| Only the first volume of a multi-volume RAR set is extracted                      | `unrar` follows the chain from there. Every part of a `name.partN.rar` set matches the search expression, so later parts are filtered by volume number: `part1`, `part01` and `part001` are all first volumes, compared as base 10 so `part08` is not read as octal. Old-style `.r00`/`.r01` volumes do not match at all |
| The search matches files only                                                     | A directory named like an archive would otherwise be handed to an extractor, and `--delete-archives` would `rm -f` a directory and fail                                                                                                                                                                                  |

## Notes

| Constraint                        | Detail                                                                                                                                                                                                   |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A second play, not `delegate_to`  | The controller is the host being configured: the `torrent_local_*` vars describe it, so they live in the controller's `host_vars/`                                                                       |
| Scripts cover the whole group     | They name every host in `groups['torrent']` whatever the `--limit`, but only a run reaching the controller rewrites them: after adding a torrent host, run `make torrent -- --limit faramir_controller`  |
| `torrent_root_directory` per host | The controller play reads it through `hostvars`, where the role defaults are not available, so a torrent host that does not set it is refused by name                                                    |
| No `localhost` in the inventory   | It would be included in every `hosts: all` play                                                                                                                                                          |
| Templates are ShellChecked        | The `shell` check in [tests/lint.sh](../../tests/lint.sh) renders Jinja2 expressions to placeholders, then runs ShellCheck. Suppress a finding with a `# shellcheck disable=...` comment in the template |
| The lint render is not Jinja2     | It is a `sed` approximation, so a template Jinja2 cannot render still passes CI. Bash that opens a Jinja tag breaks the render: `${#var}` starts a Jinja comment                                         |

## Operations

```bash
# Attach to the rtorrent UI on a torrent host
tmux -L rtorrent attach -t rtorrent
```
