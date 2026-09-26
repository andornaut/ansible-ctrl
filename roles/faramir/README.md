# ansible-role-faramir

Installs the [faramir](https://github.com/andornaut/faramir) secret broker, so a coding agent on a host cannot read
the credentials kept there. faramir's own [README](https://github.com/andornaut/faramir#readme) covers its threat
model, accounts, units, config model and store; this covers what is specific to this repo.

## Usage

```bash
make faramir    # install the broker on each faramir host, then authorize the controller's key on the fleet
```

An operator action. Log out and back in after the first install: it adds you to `faramir_client_group`, and group
membership is read at login.

|                                          | Controller                               | Every other faramir host                       |
| ---------------------------------------- | ---------------------------------------- | ---------------------------------------------- |
| Inventory                                | in `faramir_controller` and in `faramir` | in `faramir`                                   |
| Blocked paths, linked secrets, redaction | yes                                      | yes                                            |
| Checkout enrolled with `enrol`           | yes                                      | no, it runs no playbook                        |
| SSH key authorized on the fleet          | yes                                      | no, one is generated and no host authorizes it |
| Reached by a brokered playbook run       | no, `--limit '!faramir_controller'`      | yes, like any managed host                     |

`faramir.yml`'s first play installs the broker on the `faramir` group. The second, against `all`, authorizes the
controller's key and NOPASSWD sudo for the ansible account, pins host keys, then pings the fleet through the broker.

| Constraint                     | Detail                                                                                                                                                            |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `sudo make faramir`            | Connects with the broker's key, so it reaches only hosts that already authorize it. Run the first install, a key rotation, and a new or rebuilt host unprivileged |
| No brokered run                | `faramir run -- sudo make faramir` fails: `init` runs a second brokered command, which is refused while the first holds the escalation                            |
| Unreachable hosts              | Dropped, and each keeps whatever key it already authorized. Re-run once it is up, and run with every host reachable after generating a new key                    |
| One controller                 | The `faramir_controller` group must hold exactly one host, which must be in `faramir`                                                                             |
| Removing a host from `faramir` | Does not uninstall it. `faramir init` creates accounts and units that only an operator removes                                                                    |

## Tags

| Tag      | Description                              |
| -------- | ---------------------------------------- |
| `broker` | `tasks/broker.yml`: install the broker   |
| `ssh`    | `tasks/ssh.yml`: authorize the fleet key |

The tags apply only when the role is applied whole: `faramir.yml` imports each half with `tasks_from`.

## Variables

See [defaults/main.yml](./defaults/main.yml).

| Variable                             | Purpose                                                                                                                             |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| `faramir_release_tag`                | Release to install. `dev` (default) is the rolling release cut on every push to faramir's `main`; a version tag (`v0.5.0`) pins one |
| `faramir_client_group`               | Group that gives the agent and the service accounts the working tree. Default `dev`                                                 |
| `faramir_agents`                     | Agents passed to `init` and `enrol`. See [Agents](#agents)                                                                          |
| `faramir_allow_sudo`                 | Lets a brokered command ask to sudo on the controller. See [Notes](#notes)                                                          |
| `faramir_sudo_timeout_sec`           | Seconds an escalation waits for an answer, 1 to 600. Default `600`                                                                  |
| `faramir_notify_command`             | Command announcing a waiting escalation, one element per argument. Only with `faramir_allow_sudo`. See [Notes](#notes)              |
| `faramir_ptrace_scope`               | `kernel.yama.ptrace_scope`. Default `1`; `~` leaves the host's value. faramir refuses `0`                                           |
| `faramir_blocked_home_paths`         | Paths blocked under every home. See [Blocked home paths](#blocked-home-paths)                                                       |
| `faramir_blocked_system_paths`       | Absolute paths outside any home. Set in `host_vars`                                                                                 |
| `faramir_shared_user_homes`          | Other accounts' homes, absolute, no trailing slash. Set in `group_vars/faramir.yml`                                                 |
| `faramir_blocked_commands`           | Commands blocked to the agent's shell and to brokered commands. See [Blocked commands](#blocked-commands)                           |
| `faramir_links`                      | Credentials read where their own tool keeps them. Set in `host_vars`. Each: `ref`, `path`, `type`, and `key` for types that select  |
| `faramir_user_home_mode`             | Mode of the agent's home, default `0710`                                                                                            |
| `faramir_fleet_known_hosts_path`     | Where the fleet's host keys are pinned. Default `/etc/ssh/ssh_known_hosts`                                                          |
| `faramir_fleet_authorized_keys_path` | Unset: `~/.ssh/authorized_keys`, or `/root/.ssh/authorized_keys2` on routers. Set per host for another that regenerates the former  |
| `faramir_fleet_authorize_key`        | Per host. Default `true`; `false` removes the broker's key and the NOPASSWD sudo entry from that host                               |

## Installed files

`faramir init` creates the accounts, age key, `.sops.yaml`, SSH identity, directories, config and units. The role adds:

| Path or step                           | Purpose                                                                                    |
| -------------------------------------- | ------------------------------------------------------------------------------------------ |
| sops                                   | From its release `.deb`                                                                    |
| `/usr/local/bin/faramir`               | From the release named by `faramir_release_tag`                                            |
| Block and link entries                 | See [Blocked paths and linked secrets](#blocked-paths-and-linked-secrets)                  |
| Enrolment (controller)                 | `faramir enrol` against the checkout                                                       |
| `AGENTS.md` block (controller)         | How to run these playbooks through the broker                                              |
| `/etc/sysctl.d/60-faramir-ptrace.conf` | `faramir_ptrace_scope`                                                                     |
| `faramir doctor`                       | Run and asserted on. The controller also prints the public key the second play distributes |

## Running playbooks

Playbooks that read a credential run under `sops exec-env`. Once the broker is installed the operator cannot read the
store, so `make <playbook>` re-runs itself as root (`sudo bin/playbook.py run <playbook>`), which reads the store and
connects with the broker's key. The one password prompt comes before anything applies. The store is looked up under
`FARAMIR_OPERATOR`'s home on a brokered run, `SUDO_USER`'s under a typed `sudo`, and the invoking account's otherwise.

The agent's route takes no password and cannot configure the controller:

```bash
faramir run --env-file faramir.env -- ansible-playbook <playbook>.yml --limit '!faramir_controller'
```

Where `faramir_allow_sudo` is set, the controller is reachable with one approval for the whole run, no
`--env-file` needed:

```bash
faramir run -- sudo make <playbook>
```

## Blocked paths and linked secrets

By default an install blocks only faramir's own directories and commands (`faramir block ls --built-in`).
Everything else is covered only if these lists declare it, and nothing reports what is missing.

|                                             | A block entry                           | A `faramir_links` entry |
| ------------------------------------------- | --------------------------------------- | ----------------------- |
| Names                                       | a path or a command                     | a ref and a path        |
| Blocked to the agent's file tools and shell | yes                                     | yes                     |
| Refused to brokered commands                | with `--strict` (paths), yes (commands) | yes                     |
| Redacted wherever it appears                | no                                      | yes                     |
| Injectable by ref                           | no                                      | yes                     |

| Constraint                     | Detail                                                                                                                                                                                                                                                                                        |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Declared under every home      | Each home path is declared under the operator's home and each of `faramir_shared_user_homes`                                                                                                                                                                                                  |
| Declared on every faramir host | An entry is enforced where the command is typed, not where the file is ([faramir docs](https://github.com/andornaut/faramir/blob/main/docs/configuration.md#where-an-entry-is-enforced)), and the ansible account has NOPASSWD sudo on every managed host                                     |
| Path syntax                    | Relative to the home, no leading slash or `~`. A directory blocks everything under it. One wildcard: a trailing `*` after at least one literal character (`ssfn*`, `id_*`). Symlinks are not resolved: declare each spelling. A path inside a container cannot be declared                    |
| Any mention is refused         | `ls`, `stat` or an `echo` quoting a declared path is refused, as is a shell glob that could reach it                                                                                                                                                                                          |
| `--strict`                     | Paths and links are written `--strict`, which also refuses brokered `chmod`, `chown`, `rm` and in-place use (`ssh -i`, `--password-file`). Rotate such a key or fix its mode at a terminal                                                                                                    |
| Command syntax                 | Literal words; any whitespace between them. It matches where a command starts, including after `sudo`, `env` or `VAR=value`. A flag between two words defeats a longer entry, so spell out each alternative                                                                                   |
| No name patterns               | `*.key`, `*.pem`, `.env*` and the like cannot be declared. Name the directory instead                                                                                                                                                                                                         |
| Absent paths                   | Every path is declared whether or not the host has it. The run prints, per home, how many are present; a home with none is likely a misspelled account. `-v` names each absent path                                                                                                           |
| Blocks converge both ways      | A block not in the lists is removed, a hand-added one included                                                                                                                                                                                                                                |
| Links: use sparingly           | A linked file that exists but cannot be read makes the broker refuse every `run` and `redact`. A tool that rewrites its file by rename drops the broker's read until `make faramir` restores it, or `sudo faramir reload` after a fix. Prefer a block where nothing asks for the value by ref |
| Links replace blocks           | A link covers everything a block does, so a path this host links is not also blocked                                                                                                                                                                                                          |
| `faramir_links` in `host_vars` | `link add` refuses a missing file, so a link belongs only to hosts that have it                                                                                                                                                                                                               |
| `faramir_links` is add-only    | To drop a link, remove it from `faramir_links` and run `link rm` by hand                                                                                                                                                                                                                      |

### Blocked home paths

What each `faramir_blocked_home_paths` entry covers. Several are absent on every host; the rule holds when the file
appears.

| Entries                                                                                                                                                                                                                                                                                 | Holds                                                                               | Shape                                                                                                                |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `.private`, `.gnupg`, `.local/share/keyrings`                                                                                                                                                                                                                                           | The operator's credential store, keys and keyrings                                  | Directories                                                                                                          |
| `.local/share/mrs`                                                                                                                                                                                                                                                                      | mrs vaults and their `.bak` copies                                                  | Directory. `mrs` is also a [blocked command](#blocked-commands)                                                      |
| `.pki`, `.local/share/pki`                                                                                                                                                                                                                                                              | NSS databases: client certificates and their keys                                   | Both locations nss uses                                                                                              |
| `.config/sops`, `.age`                                                                                                                                                                                                                                                                  | age identities                                                                      | Directories                                                                                                          |
| `.netrc`, `.pgpass`                                                                                                                                                                                                                                                                     | Plaintext passwords for ftp, curl, git and libpq                                    | Files                                                                                                                |
| `.kube/config`                                                                                                                                                                                                                                                                          | Cluster certificates, keys and tokens                                               | The file                                                                                                             |
| `.ssh/id_*`                                                                                                                                                                                                                                                                             | SSH private keys                                                                    | The `ssh-keygen` prefix, so `config` and `known_hosts` stay readable. A key named off the prefix needs its own entry |
| `.config/MQTT-Explorer`, `.irssi`                                                                                                                                                                                                                                                       | Plaintext broker and IRC passwords                                                  | Directories                                                                                                          |
| `.config/google-chrome*`, `.config/chromium`                                                                                                                                                                                                                                            | Chromium-family profiles: saved passwords, cookies, cards                           | The prefix covers every Chrome channel                                                                               |
| `.var/app/org.mozilla.firefox`, `.mozilla`, `.var/app/org.chromium.Chromium`                                                                                                                                                                                                            | Browser profiles                                                                    | One entry per install method                                                                                         |
| `.var/app/org.filezillaproject.Filezilla`                                                                                                                                                                                                                                               | Encoded site passwords                                                              | Flatpak only. An apt install needs `.config/filezilla` added                                                         |
| `.config/Insync`, `.config/itch`                                                                                                                                                                                                                                                        | Sync and storefront session tokens                                                  | Directories                                                                                                          |
| `.var/app/io.github.wyze3306.BedrockOnLinux`                                                                                                                                                                                                                                            | A Microsoft account token                                                           | Whole                                                                                                                |
| `.var/app/net.lutris.Lutris/...`                                                                                                                                                                                                                                                        | Storefront sign-ins, the lutris.net token and the sign-in view's sessions           | File by file: logs, `pga.db`, game and runner configs and caches stay readable                                       |
| Steam (flatpak and native)                                                                                                                                                                                                                                                              | Refresh tokens, store cookies, `local.vdf`, the `ssfn` sentry, `.steam/steam.token` | See [Steam](#steam)                                                                                                  |
| `.var/app/com.heroicgameslauncher.hgl/...`                                                                                                                                                                                                                                              | Storefront backends' credentials and the Electron view's sessions                   | File by file: game configs, store caches and tools stay readable                                                     |
| `.vim/tmp`, `.viminfo`                                                                                                                                                                                                                                                                  | vim's persisted registers, which can hold text yanked from a decrypted file         | The dotfiles' `viminfofile` and vim's default                                                                        |
| `.npmrc`, `.config/pypoetry/auth.toml`, `.git-credentials`, `.config/git/credentials`, `.cargo/credentials.toml`                                                                                                                                                                        | Registry and package-index tokens                                                   | Files. A link replaces the `.npmrc` block where one exists                                                           |
| `.claude/.credentials.json`, `.codex/auth.json`, `.local/share/opencode/auth.json`, `.continue/config.yaml`, `.gemini/config/config.json`, `.pi/agent/auth.json`, `.local/share/kilo/auth.json`, `.config/cursor/auth.json`, `.gemini/oauth_creds.json`, `.gemini/google_accounts.json` | Each agent's signed-in token or inline provider key                                 | Files                                                                                                                |
| `.config/kilo/kilo.json[c]`, `.config/opencode/opencode.json[c]`                                                                                                                                                                                                                        | Inline provider keys, and faramir's deny rules for those agents                     | Both extensions. Adding a model provider is the operator's at a terminal                                             |
| `.config/gh/hosts.yml`, `.clasprc.json`                                                                                                                                                                                                                                                 | The GitHub CLI's token and clasp's Google refresh token                             | `hosts.yml` only: `config.yml` holds settings an agent edits                                                         |
| `.docker/config.json`                                                                                                                                                                                                                                                                   | Registry auth                                                                       | Blocked, not linked: `docker login` replaces the file by rename                                                      |
| `.claude.json`                                                                                                                                                                                                                                                                          | Claude Code's config, including MCP server environments                             | The file, not `.claude/`                                                                                             |
| `.claude/daemon`, `.claude/sessions`                                                                                                                                                                                                                                                    | Daemon and session socket keys                                                      | Two directories, not `.claude/`                                                                                      |
| `.bashrc.private`                                                                                                                                                                                                                                                                       | Shell environment kept out of the committed `bashrc`                                | File                                                                                                                 |
| `.android/adbkey`                                                                                                                                                                                                                                                                       | The adb private key                                                                 | The file; the public half stays readable                                                                             |
| `.zoom/data`, `.var/app/com.discordapp.Discord`, `.local/share/Insync`                                                                                                                                                                                                                  | Signed-in sessions kept outside a keyring                                           | Directories                                                                                                          |
| `.gnome/.gem/credentials`, `.local/share/gem/credentials`                                                                                                                                                                                                                               | The RubyGems API key                                                                | Both locations gem reads                                                                                             |
| `.vscode-shared/sharedStorage`                                                                                                                                                                                                                                                          | The editors' shared secret store                                                    | Directory                                                                                                            |
| `.clipboard`, `.var/app/app.getclipboard.Clipboard`                                                                                                                                                                                                                                     | Clipboard history                                                                   | Directories                                                                                                          |
| `.config/Code`, `.config/Cursor`, `.config/Antigravity`, `.config/Claude`                                                                                                                                                                                                               | Electron profiles: sessions, secret stores, local history of every saved file       | Whole, so `settings.json`, keybindings and MCP config are the operator's to edit at a terminal                       |
| `.config/uhk-agent`, `.config/ExpressLRS Configurator`, `.config/betaflight-configurator`, `.local/share/org.coolercontrol.CoolerControl`                                                                                                                                               | Vendor-account cookie jars                                                          | Whole                                                                                                                |
| `.minecraft/webcache`                                                                                                                                                                                                                                                                   | The launcher's account session                                                      | The rest of `.minecraft` stays readable                                                                              |

Game launchers other than Steam are declared only at their flatpak paths; an apt install of Lutris or Heroic needs
`~/.cache/lutris` or `~/.config/heroic` added.

#### Steam

| Constraint     | Detail                                                                                                                                                                                      |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Four spellings | The flatpak's `data` and `.local/share`, the native `.local/share/Steam`, and each `.steam` symlink. Symlinks are declared whole, which also blocks the directory each resolves to entirely |
| Readable       | `steamapps`, `appcache`, `compatdata`, `userdata` and `config/libraryfolders.vdf`, through whichever canonical spelling no symlink resolves to. `faramir block ls` shows what is refused    |
| `ssfn*`        | The full name carries a per-account number                                                                                                                                                  |

### Blocked commands

| Entries                                                                          | Reason                                                                             | Still allowed                    |
| -------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | -------------------------------- |
| `gh auth token`, `gh auth status`                                                | Print the GitHub CLI's token (`status` with `-t`)                                  |                                  |
| `gh auth git-credential`                                                         | Returns the token through the git credential helper protocol                       |                                  |
| `mrs`                                                                            | The operator's vault manager: `export` and `search` print secrets, `edit` decrypts | `vault list` and `vault default` |
| `op read`, `op item get`, `op inject`, `pass show`, `vault read`, `vault kv get` | Print a secret                                                                     |                                  |
| `gopass`                                                                         | Every subcommand                                                                   |                                  |

## Agents

`faramir_agents` names every agent the [dev role](../dev/README.md) installs that faramir can configure. They are
named explicitly because faramir's `auto` covers an agent only after it has run once unguarded.

| Agent       | In this tree                                                                                 | In the operator's home                                                                                | Redaction |
| ----------- | -------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | --------- |
| claude      | `PreToolUse` hook and deny rules in `.claude/settings.local.json`, MCP server in `.mcp.json` | deny rules in `.claude/settings.json`, a credentials section in `.claude/CLAUDE.md`                   | full      |
| codex       | `PreToolUse` hook in `.codex/hooks.json`; credentials section in `AGENTS.md`                 | a deny-only `PreToolUse` hook in `.codex/hooks.json`, a credentials section in `.codex/AGENTS.md`     | full      |
| opencode    | plugin in `.opencode/plugins/`, MCP server in `opencode.json`                                | deny rules in `.config/opencode/opencode.json`, a credentials section in `.config/opencode/AGENTS.md` | full      |
| kilocode    | plugin in `.kilo/plugin/`, MCP server in `kilo.json`                                         | deny rules in `.config/kilo/kilo.json`, a credentials section in `.kilocode/rules/faramir.md`         | full      |
| pi          | extension in `.pi/extensions/`, which carries the deny rules                                 | a credentials section in `.pi/agent/AGENTS.md`                                                        | full      |
| antigravity | MCP server in `.agents/mcp_config.json`, credentials section in `.agents/rules/faramir.md`   | a credentials section in `.gemini/GEMINI.md`                                                          | none      |

| Constraint                   | Detail                                                                                                                                            |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Antigravity is partial       | Its hooks can refuse a tool call but not rewrite it, so its commands are neither brokered nor redacted                                            |
| Codex must trust the hook    | Start Codex once and trust the hook before the enrolment has any effect. It must run without its own sandbox                                      |
| Cursor                       | Not configured by faramir, so a credential one of its commands prints reaches the model                                                           |
| Bash prompts (claude, codex) | The hook approves every command the deny list does not name                                                                                       |
| Deny-list pruning            | Temporary migration (`tasks/prune.yml`): deletes every deny entry faramir's record does not name, hand-added ones included, keeping a `.bak` copy |

## Notes

| Constraint                        | Detail                                                                                                                                                                                                                                                       |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Encrypted home must be mounted    | `~/.config/faramir` holds the age key, the broker's key and the store. On an ecryptfs host the run fails unless the home is mounted, rather than writing them onto the mountpoint in the clear. Log in first                                                 |
| One store                         | Every credential lives in `~/.config/faramir/secrets/ansible-ctrl.sops.yml` on the controller. One held elsewhere is neither injectable nor redacted unless a `faramir_links` entry reads it                                                                 |
| Storeless hosts                   | The first managed file comes from `sudo faramir vault add NAME`. A host whose values all come from links needs no store                                                                                                                                      |
| Store location                    | Never under `group_vars/`, `host_vars/` or the checkout: Ansible would load its ciphertext, and the checkout is public                                                                                                                                       |
| Brokered runs skip the controller | A brokered play would ask once per `become` task on the controller. Use the single approval in [Running playbooks](#running-playbooks)                                                                                                                       |
| `sudo` version                    | The grant needs sudo 1.9.11 or sudo-rs 0.2.9; on an older host `init` names the floor and writes nothing                                                                                                                                                     |
| Escalation timeout                | While an escalation waits, every other brokered command on the host is refused. Only the literal answer the prompt names approves; no answer is a refusal                                                                                                    |
| `faramir_allow_sudo`              | Approval is per command, at `sudo faramir sudo watch`; no password exists anywhere. Setting it also drops the executor unit's seccomp filter and `ProtectSystem=strict` for every brokered command. `false` removes the grant                                |
| `faramir_notify_command`          | Must name `{prompt}` or `{id}`; keep `{id}` off anything that broadcasts, since `wall` reaches the agent's terminal too. It runs with a fixed `PATH` and no access to the operator's session: `wall` and network requests work, desktop notifications do not |
| Pinned host keys                  | A fleet host key that stops matching fails the play; it is not rewritten                                                                                                                                                                                     |
| Router keys                       | Routers get the broker's key in `/root/.ssh/authorized_keys2` (pfSense regenerates `authorized_keys`) and no sudoers entry                                                                                                                                   |

## Setup

- Add a host by putting it in the `faramir` group, then run `make faramir` unprivileged.
- Set `faramir_shared_user_homes` in `group_vars/faramir.yml` for any other account whose files must be blocked.
- Set `faramir_links` in the host's `host_vars` for credentials another tool keeps in place.

## Operations

```bash
cd <dir> && sudo faramir enrol # Enrol another tree
sudo faramir reload            # Re-read a linked file whose group or mode the run corrected, outside any faramir run
```

## Verification

Run from the repository root, where the vars plugin finds `faramir.env`:

```bash
faramir run --env-file faramir.env -- \
    ansible <host> -m debug -a 'var=msmtp_password'
# -> "msmtp_password": "«SECRET:msmtp_password»"
```

| Output                     | Meaning                                      |
| -------------------------- | -------------------------------------------- |
| `«SECRET:...»`             | the chain works end to end                   |
| `VARIABLE IS NOT DEFINED!` | the ref was not injected                     |
| `ENC[AES256_GCM,...]`      | the encrypted file is where Ansible loads it |

`sudo faramir doctor` adds the boundary checks, which need a uid other than your own.
