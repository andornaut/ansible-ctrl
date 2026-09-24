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

One role, two kinds of install:

|                                          | Controller                               | Every other faramir host                       |
| ---------------------------------------- | ---------------------------------------- | ---------------------------------------------- |
| Inventory                                | in `faramir_controller` and in `faramir` | in `faramir`                                   |
| Blocked paths, linked secrets, redaction | yes                                      | yes                                            |
| Checkout enrolled with `enrol`           | yes                                      | no, it runs no playbook                        |
| SSH key authorized on the fleet          | yes                                      | no, one is generated and no host authorizes it |
| Reached by a brokered playbook run       | no, `--limit '!faramir_controller'`      | yes, like any managed host                     |

The second kind is for a host that runs no playbook and only keeps its own credentials from an agent.

`faramir.yml` applies the role's two entry points in order:

| Play   | Entry point                       | Hosts     | Effect                                                                                                     |
| ------ | --------------------------------- | --------- | ---------------------------------------------------------------------------------------------------------- |
| first  | `tasks/broker.yml` (`tasks_from`) | `faramir` | Installs the broker                                                                                        |
| second | `tasks/ssh.yml` (`tasks_from`)    | `all`     | Authorizes the controller's key and NOPASSWD sudo, pins host keys, then pings the fleet through the broker |

| Constraint                     | Detail                                                                                                                                                                                                                                                                                                     |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `sudo make faramir`            | Connects with the broker's key, not `~/.ssh`, so it reaches only hosts that already authorize that key. Run the first install, a key rotation, and a new or rebuilt host unprivileged. Root avoids one approval per `become` task on the controller, whose sudo authenticates through faramir's PAM helper |
| No brokered run                | `faramir run -- sudo make faramir` holds an escalation on the executor's uid, and `init`'s validate step is a second brokered command, which is refused while the first waits                                                                                                                              |
| Unreachable hosts              | Preflight drops them, and each keeps whatever key it already authorized. Under a root run the probe uses the broker's key, so a host that has not authorized it is dropped the same way. Re-run once it is up, and run with every host reachable after generating a new key                                |
| One controller                 | `faramir_controller_host` is derived from the `faramir_controller` group, which must hold exactly one host running the broker; `ssh.yml` asserts both. `faramir_is_controller` gates the controller-only tasks                                                                                             |
| `broker.yml` scope             | Refuses a host outside the `faramir` group                                                                                                                                                                                                                                                                 |
| Removing a host from `faramir` | Does not uninstall it. `faramir init` creates accounts and units that only an operator removes                                                                                                                                                                                                             |

## Tags

| Tag      | Description                              |
| -------- | ---------------------------------------- |
| `broker` | `tasks/broker.yml`: install the broker   |
| `ssh`    | `tasks/ssh.yml`: authorize the fleet key |

The tags apply only when the role is applied whole. `faramir.yml` imports each half with `tasks_from`, which carries
neither tag.

## Variables

See [defaults/main.yml](./defaults/main.yml). The service accounts and the broker's SSH key path follow faramir's
defaults and are not variables here.

| Variable                             | Purpose                                                                                                                                              |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `faramir_release_tag`                | Release to install. `dev` (default) is the rolling release; a version tag pins one. See [Installed files](#installed-files)                          |
| `faramir_client_group`               | Group that gives the agent and the service accounts the working tree. Default `dev`                                                                  |
| `faramir_agents`                     | Agents passed to `init` and `enrol`. See [Agents](#agents)                                                                                           |
| `faramir_allow_sudo`                 | Lets a brokered command ask to sudo on the controller. Also drops the executor unit's seccomp filter and `ProtectSystem=strict`                      |
| `faramir_sudo_timeout_sec`           | Seconds an escalation waits for an answer, 1 to 600. Default `600`                                                                                   |
| `faramir_notify_command`             | Command announcing a waiting escalation, one element per argument. Only with `faramir_allow_sudo`                                                    |
| `faramir_ptrace_scope`               | `kernel.yama.ptrace_scope`. Default `1`; `~` leaves the host's value                                                                                 |
| `faramir_blocked_home_paths`         | Paths blocked under every home. See [Blocked paths and linked secrets](#blocked-paths-and-linked-secrets)                                            |
| `faramir_shared_user_homes`          | Other accounts' homes, absolute. Set in `group_vars/faramir.yml`                                                                                     |
| `faramir_blocked_commands`           | Commands blocked to the agent's shell and to brokered commands                                                                                       |
| `faramir_links`                      | Credentials read where their own tool keeps them. Set in `host_vars`                                                                                 |
| `faramir_fleet_known_hosts_path`     | Where the fleet's host keys are pinned. Default `/etc/ssh/ssh_known_hosts`                                                                           |
| `faramir_fleet_authorized_keys_path` | Unset: `~/.ssh/authorized_keys`, or `/root/.ssh/authorized_keys2` on routers. Set in `host_vars` for another host that regenerates `authorized_keys` |

## Installed files

`faramir init` creates the accounts, age key, `.sops.yaml`, SSH identity, directories, config and units. The role adds:

| Path or step                           | Purpose                                                                                                                                                                                                              |
| -------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| sops                                   | From its release `.deb`, checked against GitHub's SHA-256 digest for the asset: sops' `checksums.txt` lists its binaries, not its `.deb`s. No age package: sops links the library and `init` generates the keypair   |
| `/usr/local/bin/faramir`               | From the release named by `faramir_release_tag`, checked against that release's `checksums.txt`. The tag is named, not resolved: `dev` is published with `make_latest=false`, so `/releases/latest` never returns it |
| Block and link entries                 | `tasks/entries.yml`. See [Blocked paths and linked secrets](#blocked-paths-and-linked-secrets)                                                                                                                       |
| Enrolment (controller)                 | `faramir enrol` against `playbook_dir`                                                                                                                                                                               |
| `AGENTS.md` block (controller)         | How to run these playbooks through the broker                                                                                                                                                                        |
| Agent deny lists                       | Pruned by `files/prune-agent-rules.py`. See [Agents](#agents)                                                                                                                                                        |
| `/etc/sysctl.d/60-faramir-ptrace.conf` | Pins `kernel.yama.ptrace_scope`, so one brokered command cannot ptrace another and read the values injected into it                                                                                                  |
| `faramir doctor`                       | Run and asserted on. The controller also prints the public key the second play distributes                                                                                                                           |

## Running playbooks

`homeautomation`, `msmtp` and `webservers` read a credential and re-enter under `sops exec-env`. The other targets
run directly. Once the broker is installed the operator cannot read the store, and `make` handles that:

| Run                          | What `make <playbook>` does                               |
| ---------------------------- | --------------------------------------------------------- |
| no credential                | one `ansible-playbook`, as the operator                   |
| credential, store readable   | one `ansible-playbook`, under `sops exec-env`             |
| credential, store unreadable | `sudo bin/playbook.py run <playbook>`, then the row above |

Root reads the store itself, and `ANSIBLE_PRIVATE_KEY_FILE` gives it the broker's key, which every managed host
authorizes. The one password prompt comes before anything applies.

The paths resolve under this home:

| Context                      | Home resolved from   |
| ---------------------------- | -------------------- |
| Brokered run (`faramir run`) | `FARAMIR_OPERATOR`   |
| Typed `sudo`                 | `SUDO_USER`          |
| Unprivileged run             | the invoking account |

On a brokered run `SUDO_USER` is the executor account, so `FARAMIR_OPERATOR` takes precedence there. A root run of a
credential-reading playbook that cannot read the store at the resolved path refuses and names the path: the store
is missing there, or the home is not mounted.

The agent's route takes no password:

```bash
faramir run --env-file faramir.env -- ansible-playbook <playbook>.yml --limit '!faramir_controller'
```

`faramir.env` holds refs, never values.

Where `faramir_allow_sudo` is set, the controller is reachable with one approval:

```bash
faramir run -- sudo make <playbook>
```

One approval covers the run: no per-task prompt and no `--ask-become-pass`. Root reads the store itself, so this
route needs no `--env-file`. The sudo environment comes from the file the grant names, not from the caller:
`[command] env` passes through, and `FARAMIR_OPERATOR` names the operator on both sides.

## Blocked paths and linked secrets

faramir compiles in no credential rules. By default an install blocks only its own directories at their real paths:
the config directory, the store, `/var/log/faramir`, `/usr/local/libexec/faramir` and the service accounts' state
directories. Everything else is covered only if these lists declare it, and nothing reports what is missing: find a
gap by checking a host's files against the lists. `tasks/entries.yml` converges them.

| List                         | Entry     | Reaches                                 | Checked against the host                            |
| ---------------------------- | --------- | --------------------------------------- | --------------------------------------------------- |
| `faramir_blocked_home_paths` | `path`    | the agent's file tools and its shell    | no; a rule for an absent path holds once it appears |
| `faramir_blocked_commands`   | `command` | the agent's shell and brokered commands | no                                                  |

|                                                | A block entry                | A `faramir_links` entry                                    |
| ---------------------------------------------- | ---------------------------- | ---------------------------------------------------------- |
| Config entry                                   | `[[secret.block]]`           | `[[secret.link]]`                                          |
| Names                                          | a path or a command          | a ref, a path, a type, and a key for the types that select |
| Blocked to the agent's file tools              | yes, except a command        | yes                                                        |
| Regrouped, so a brokered command is refused it | no, the mode is left alone   | yes                                                        |
| In the redactor, tokenised wherever it appears | no, the file is never opened | yes                                                        |
| Injectable by ref                              | no                           | yes                                                        |

| Constraint                        | Detail                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Declared under every home         | `vars/main.yml` joins each entry to the operator's home and to each of `faramir_shared_user_homes`, so each extra account doubles the entries, most of them absent. A path is literal: the same store at another depth needs its own entry                                                                                                                                                                                                                                       |
| Declared on every faramir host    | An entry is enforced on the host where the command is typed, not where the file is ([faramir docs](https://github.com/andornaut/faramir/blob/main/docs/configuration.md#where-an-entry-is-enforced)). `faramir.yml` gives the ansible account NOPASSWD sudo on every managed host, so `ssh <host> sudo cat <path>` reaches another account's files. A faramir host outside `dev` runs no agent; the entry is declared there so a host added to `dev` is covered on its first run |
| `faramir_shared_user_homes`       | Empty in defaults and set in `group_vars/faramir.yml`, since an account name is inventory data. Asserted to be a list of absolute homes with no trailing slash: a bare string would be joined one character at a time                                                                                                                                                                                                                                                            |
| Shape: relative, shortest form    | No leading slash and no `~`, which nothing expands. A directory blocks everything under it, whether or not it exists when the rule is written. The run prints each entry's warnings                                                                                                                                                                                                                                                                                              |
| Finer shape beside readable files | `.ssh/id_*`, not `.ssh/`, because the agent opens `config` and `known_hosts`. The same for each editor's `User/globalStorage` against its settings and MCP config, and for an agent's token against its instruction file. No exception can be made inside a directory rule, so under other accounts a key not matching `id_*` is not covered: add its path here                                                                                                                  |
| Any mention is refused            | The agent is refused a declared path whatever the command does with it: `ls`, `stat`, `chmod` and an `echo` quoting the path alike, in its file tools and its shell. There is no verb list. A shell pattern that could reach a declared file is refused too: with `~/.npmrc` declared, a glob over the home is refused and `ls ~/*.md` is not. The pattern is not expanded; its literal parts are compared with the declared name                                                |
| `--strict`                        | Path entries and links are written `--strict`; commands cannot be, faramir refusing the pair. The flag applies only to brokered commands. Reading, `mv` and `ln` on a declared file are refused either way. `--strict` also refuses `chmod`, `chown`, `rm`, `truncate`, a redirect over the file, and using it in place (`cryptsetup --key-file`, `ssh -i`, `restic --password-file`). So rotating such a key or fixing its mode is done by the operator at a terminal           |
| Path syntax                       | Absolute. One wildcard: a trailing `*` on the last component after at least one literal character (`ssfn*`, `id_*`). A store with no fixed location cannot be declared, nor a file an agent opens inside a container, where the path is the mount point's. Symlinks are not resolved: declare each name. `defaults/main.yml` lists what stays uncovered                                                                                                                          |
| Command syntax                    | Literal words; a space matches any run of whitespace. Spell out each alternative as its own entry                                                                                                                                                                                                                                                                                                                                                                                |
| Command matching                  | Matches where a command starts: line start, after a separator, or after a prefix that runs something else (`sudo`, `env`, `VAR=value`). A bare word covers every use of the tool but not the word inside a flag or path; a subcommand narrows it to that use. `block ls` reports each command entry as refused to the agent's shell and to brokered commands                                                                                                                     |
| Absent paths                      | Every blocked path is written whether or not the host has it, so a tool signed in after a run is covered. The run warns per absent path, and a misspelled path warns the same way: check the warnings against the list. An entry is added where a host has, or a role installs, the tool that writes the file                                                                                                                                                                    |
| Links: use sparingly              | A linked file that exists but cannot be read makes the broker refuse `run` and `redact` for every ref. A tool that rewrites its file by rename removes the broker's read grant until `make faramir` restores it. Prefer a block where nothing asks for the value by ref                                                                                                                                                                                                          |
| Links replace blocks              | A link renders the same rule as a block plus three more, so `vars/main.yml` drops the block entry for a path this host links: `~/.npmrc` stays blocked on a `dev` host with no link, and is a link where there is one. The link is kept because it carries the ref                                                                                                                                                                                                               |
| `faramir_links` in `host_vars`    | `link add` refuses an entry whose file is absent, so a link in defaults would fail on a host without the file. Blocked paths are written and warned about, so they stay in defaults                                                                                                                                                                                                                                                                                              |
| Idempotent adds                   | Every entry is re-applied on every run, which restores a grant a tool removed and a rule an agent's settings dropped. `faramir init` re-asserts them all from `config.toml` afterwards                                                                                                                                                                                                                                                                                           |
| Release floor                     | Needs `block`, `--json`, `block ls --declared`, and `--strict` on `block add` and `link add`, which `faramir_release_tag: dev` has. An older tag fails, in some cases without an error                                                                                                                                                                                                                                                                                           |
| Order                             | Entries converge before `enrol`, which renders them into this tree's agent files. An add writes only the account-wide rule files; pi's rules are only in its per-tree extension                                                                                                                                                                                                                                                                                                  |
| Blocks converge both ways         | A run adds what the lists name and removes every declared entry they do not, read with `block ls --declared` and compared per form. A hand-added block does not survive a run. The run asserts every `kind` read back is `path` or `command`                                                                                                                                                                                                                                     |
| Removal cleans rendered rules     | `block rm` re-renders the agent rule files. faramir records what it last wrote into each (`written-rules.json`, beside the config): a rule in that record and no longer rendered is removed, and one not in the record is left as the operator's. The run names what it removed                                                                                                                                                                                                  |
| `faramir_links` is add-only       | Dropping a link changes what the host can serve, so remove it from `faramir_links` and run `link rm` by hand. `link rm` takes no `--strict`                                                                                                                                                                                                                                                                                                                                      |

## Agents

`faramir_agents` names every agent the [dev role](../dev/README.md) installs that faramir can configure, and the same
list goes to `init` and `enrol`. They are named explicitly because faramir's `auto` covers an agent only after it
has run once unguarded.

| Agent       | In this tree                                                                                 | In the operator's home                                                                                | Redaction |
| ----------- | -------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | --------- |
| claude      | `PreToolUse` hook and deny rules in `.claude/settings.local.json`, MCP server in `.mcp.json` | deny rules in `.claude/settings.json`, a credentials section in `.claude/CLAUDE.md`                   | full      |
| codex       | `PreToolUse` hook in `.codex/hooks.json`, which routes; credentials section in `AGENTS.md`   | a deny-only `PreToolUse` hook in `.codex/hooks.json`, a credentials section in `.codex/AGENTS.md`     | full      |
| opencode    | plugin in `.opencode/plugins/`, MCP server in `opencode.json`                                | deny rules in `.config/opencode/opencode.json`, a credentials section in `.config/opencode/AGENTS.md` | full      |
| kilocode    | plugin in `.kilo/plugin/`, MCP server in `kilo.json`                                         | deny rules in `.config/kilo/kilo.json`, a credentials section in `.kilocode/rules/faramir.md`         | full      |
| pi          | extension in `.pi/extensions/`, which carries the deny rules                                 | a credentials section in `.pi/agent/AGENTS.md`, and no deny rules: pi reads them from the extension   | full      |
| antigravity | MCP server in `.agents/mcp_config.json`, credentials section in `.agents/rules/faramir.md`   | a credentials section in `.gemini/GEMINI.md`, and no deny rules                                       | none      |

| Constraint                   | Detail                                                                                                                                                                                                                                                                                                                                                  |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Antigravity is partial       | Its hooks can refuse a tool call but not rewrite it, so nothing routes its commands through the broker or redacts their output. It gets the MCP tools and instructions, and every enrolment warns about this                                                                                                                                            |
| Codex relies on its hook     | It has no rule file; its `.rules` files are an exec policy that names no paths, so the hook matches every tool, not only Bash. Codex skips a hook it has not been told to trust without saying so: start Codex once and trust the hook before the enrolment has any effect. It must run without its own sandbox                                         |
| Cursor                       | Installed here and not configured by faramir, so a credential one of its commands prints reaches the model                                                                                                                                                                                                                                              |
| Bash prompts (claude, codex) | The hook rewrites each command into a sourced wrapper, which no permission rule can approve, so the hook approves it. That approval covers every command the deny list does not name. The other four have no approval to return                                                                                                                         |
| Deny-list pruning            | After every install and enrolment, `files/prune-agent-rules.py` deletes every deny entry faramir's record does not name, hand-added ones included, and copies each rewritten file to `.pruned-<stamp>.bak`. Only Claude's deny lists are string arrays, so only they change; the others are reported as skipped. The script's docstring has the details |
| Nothing is committed         | This repo's `.gitignore` covers `.claude/*` and the agents' instruction filenames; the operator's global ignore covers the rest                                                                                                                                                                                                                         |

## Notes

| Constraint                        | Detail                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Config directory                  | `~/.config/faramir` holds the age key, the broker's SSH key and the store, so an encrypted home encrypts all three. `init` grants the client group execute without read from the home down. `doctor` fails if the executor can read `~/.ssh`, `~/.config/sops` or `~/.gnupg`                                                                                                                                                               |
| Encrypted home must be mounted    | `getent` returns the home's path whether or not it is mounted, so a run against a locked home would write the keys and store onto the mountpoint in plaintext and read every credential store in the home as absent. The check looks for `<home's parent>/.ecryptfs/<user>`, which is outside the home and present either way, then requires the home among `ansible_facts["mounts"]`. Typical case: a laptop that is up but not logged in |
| One store                         | Every credential lives in the store, `~/.config/faramir/secrets/ansible-ctrl.sops.yml` on the controller. One held elsewhere is neither injectable through `--env` nor redacted, unless a `faramir_links` entry reads it where its tool keeps it                                                                                                                                                                                           |
| Storeless hosts                   | `init` creates the secrets directory, `.sops.yaml` and the age key only; the first managed file comes from `sudo faramir vault add NAME`. A host whose values all come from links needs no store                                                                                                                                                                                                                                           |
| Store location                    | Not under `group_vars/` or `host_vars/`: Ansible loads every `.yml` there, and a sops file is valid YAML, so each variable binds to its `ENC[...]` ciphertext. Not in the checkout, which is public. `faramir init` refuses both                                                                                                                                                                                                           |
| Brokered runs skip the controller | Brokered commands run as `faramir-exec`, whose only sudo is the one `faramir_allow_sudo` grants, and that asks a person per command, so a play would ask once per task. Apply the controller's playbooks as the operator or with the single approval in [Running playbooks](#running-playbooks)                                                                                                                                            |
| Either `sudo`                     | Ubuntu ships two implementations from 25.10. `init` probes the `sudo` alternatives group and writes the configuration that implementation reads. The grant sets `noninteractive_auth`, which needs sudo 1.9.11 or sudo-rs 0.2.9; on an older host `init` names the floor and writes nothing                                                                                                                                                |
| Escalation timeout                | An escalation expires after `faramir_sudo_timeout_sec`, and while one waits every other brokered command on the host is refused. Only the literal answer the prompt names approves; no answer is a refusal                                                                                                                                                                                                                                 |
| Pinned host keys                  | The executor has no `known_hosts`, so the fleet's keys go in `faramir_fleet_known_hosts_path`, keyed by the name ssh looks up (`faramir_fleet_known_hosts_name`): the bare address on port 22, `[host]:port` otherwise. A key that stops matching fails the play; it is not rewritten                                                                                                                                                      |
| Router keys                       | The routers get the broker's key in `/root/.ssh/authorized_keys2`, other hosts in the ansible account's `~/.ssh/authorized_keys`. pfSense regenerates `authorized_keys` from `config.xml` on boot and on every user save; sshd reads both. Routers log in as root, so they get no sudoers entry                                                                                                                                            |

## Setup

- Set `faramir_shared_user_homes` in `group_vars/faramir.yml` for any other account whose files must be blocked.
- Set `faramir_links` in the host's `host_vars` for credentials another tool keeps in place.

## Operations

```bash
cd <dir> && sudo faramir enrol # Enrol another tree
sudo faramir reload            # Re-read a linked file whose group or mode the run corrected, outside any faramir run
```

## Verification

Run from the repository root: an ad-hoc `ansible` command has no playbook, so the vars plugin looks for `faramir.env`
in the working directory and fails naming the file when run elsewhere.

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

`sudo faramir doctor` adds the boundary checks, which ask each account what it can reach and need a uid other than
your own.
