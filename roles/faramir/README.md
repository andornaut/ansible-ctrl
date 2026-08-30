# faramir

Installs the [faramir](https://github.com/andornaut/faramir) secret broker, so a coding agent works on a host
without being able to read the credentials kept there. What it protects against, and its accounts, units, config
model and store, are in faramir's own [README](https://github.com/andornaut/faramir#readme); this covers what is
specific to this repo.

Two kinds of install, from one role:

| | Controller | Every other faramir host |
| --- | --- | --- |
| Inventory | in `faramir_controller` and in `faramir` | in `faramir` |
| Blocked paths, linked secrets, redaction | yes | yes |
| Checkout enrolled with `init-project` | yes | no, it runs no playbook |
| SSH key authorized on the fleet | yes | no, one is minted and reaches nothing |
| Reached by a brokered playbook run | no, `--limit '!faramir_controller'` | yes, like any managed host |

The second is the install for a machine that only wants its own credentials kept out of an agent's reach.

## Usage

```bash
make faramir    # install the broker on each faramir host, then authorize the controller's key on the fleet
```

An operator action. Log out and back in after the first install: it adds you to `faramir_client_group`, and group
membership is read at login.

- **`sudo make faramir` connects with the broker's key** rather than your `~/.ssh`, so it reaches only a fleet
  that already accepts that key: not the first install, not a rotated key, and not a host added or rebuilt since
  the last run. Run those unprivileged. What root buys is the sudo: the controller's own authenticates through
  faramir's PAM helper, so an unprivileged run waits on an approval per `become` task.
- **The broker cannot run this playbook at all.** `faramir run -- sudo make faramir` holds an escalation on the
  executor's uid, and `init`'s validate step asks the broker what the agent holds, which is a second brokered
  command and is refused while the first is waiting.
- Preflight drops an unreachable host here as it does everywhere else, and a dropped host keeps whatever it
  already authorized. Under a root run it also names the identity, a host that has yet to authorize the key
  reading the same as one that is off. Re-run `make faramir` once it is back up, and after generating a new key
  run it with every host reachable.

`faramir.yml` applies the role's two entry points in order:

| Play | Entry point | Hosts | Effect |
| --- | --- | --- | --- |
| first | `tasks/broker.yml` (`tasks_from`) | `faramir` | Installs the broker on each of them |
| second | `tasks/ssh.yml` (`tasks_from`) | `all` | Authorizes the controller's key and NOPASSWD sudo, pins the fleet's host keys in `faramir_fleet_known_hosts_path`, then pings the hosts it still holds back through the broker |

`faramir_controller_host` is derived from the `faramir_controller` group rather than named here, this repo being public, and
`faramir_is_controller` is what gates the controller-only tasks. `broker.yml` refuses to run on a host outside the
`faramir` group, and `ssh.yml` requires the `faramir_controller` group to hold exactly one host and that host to be one
the broker is installed on. An install left out of `faramir` is not removed by leaving it out; `faramir init`
lays down accounts and units that only an operator takes back off.

## Variables

See [defaults/main.yml](./defaults/main.yml). The service accounts and the broker's SSH key path are left to
faramir's own defaults, so they are not knobs here.

## Running playbooks

`homeautomation`, `msmtp` and `webservers` read a credential and re-enter under `sops exec-env`. The other targets
run straight through. Once the broker is installed the store stops being readable by the operator, and `make`
routes around that:

| Run | What `make <playbook>` does |
| --- | --- |
| no credential | one `ansible-playbook`, as the operator |
| credential, store readable | one `ansible-playbook`, under `sops exec-env` |
| credential, store unreadable | `sudo make <playbook>`, then the row above |

Root reads the store itself, and `ANSIBLE_PRIVATE_KEY_FILE` gives it the broker's key, which reaches every
managed host. The one password prompt comes before anything applies.

Which home those paths resolve under is `FARAMIR_OPERATOR` where the broker sets it, `SUDO_USER` on a typed
sudo, and the invoking account on an unprivileged run. Each covers what the others get wrong: `SUDO_USER` is the
operator wherever a human typed the sudo, and the executor account on a brokered run, which is the one
`FARAMIR_OPERATOR` answers. A run that resolves the executor refuses, naming the home it looked in.

The agent's route takes no password:

```bash
faramir run --env-file faramir.env -- ansible-playbook <playbook>.yml --limit '!faramir_controller'
```

`faramir.env` holds refs and never values.

Where `faramir_allow_sudo` is set, the same route reaches the controller at the cost of one approval:

```bash
faramir run -- sudo make <playbook>
```

One question covers the run, so no per-task prompt and no `--ask-become-pass`. Root reads the store itself, so
this route needs no `--env-file`. What the sudo is given comes from the file the grant names rather than from the
caller: `[command] env` survives it, and `FARAMIR_OPERATOR` names the operator on both sides.

## Constraints

- **The config directory is `~/.config/faramir`**, holding the age key, the broker's SSH key and the store, so an
  encrypted home carries all three. `init` grants the client group traversal from the home down: execute without
  read. `doctor` fails if `~/.ssh`, `~/.config/sops` or `~/.gnupg` becomes readable by the executor.
- **An encrypted home has to be mounted, and the run stops if it is not.** `getent` answers with the home's path
  whether or not anything is mounted there, so a run against a locked home would write all three of those onto the
  mountpoint, in the clear on the underlying filesystem, and would read every credential store in that home as
  absent. The check is ecryptfs-specific: it looks for `/home/.ecryptfs/<user>`, which sits outside the home and so
  answers the same either way, and then requires the home among `ansible_facts["mounts"]`. A laptop up but not
  logged in is the case this catches.
- **Every credential lives in the store**, `~/.config/faramir/secrets/ansible-ctrl.sops.yml` on the controller.
  One held anywhere else is neither injectable through `--env` nor known to the redactor, unless a
  `faramir_links` entry reads it where its own tool keeps it.
- **A host can carry no store at all.** `faramir init` creates the secrets directory, `.sops.yaml` and the age
  key, and nothing else: the first managed file comes from `sudo faramir vault add NAME`. A host whose values all
  come from links never needs one.
- **The store must not sit under `group_vars/` or `host_vars/`**, where Ansible auto-loads every `.yml`: a sops
  file is valid YAML, so each var binds to its `ENC[...]` ciphertext and hosts get the ciphertext as the password.
  Nor in the checkout, this repo being public. `faramir init` refuses both.
- **A brokered run reaches the fleet, not the controller**, hence `--limit '!faramir_controller'`: commands run as
  `faramir-exec`, whose only sudo is the one `faramir_allow_sudo` grants, and that one asks a person per command,
  so a play would raise a question per task. Apply the controller's own playbooks as the operator, or under the
  single approval that [Running playbooks](#running-playbooks) buys.
- **`faramir_allow_sudo` works under either `sudo`.** Ubuntu ships two implementations from 25.10 on, and the
  install probes the `sudo` alternatives group and writes the arrangement that one reads. The grant sets
  `noninteractive_auth`, which needs sudo 1.9.11 or sudo-rs 0.2.9; the install names the floor and writes nothing
  on an older host.
- **An escalation expires after `faramir_sudo_timeout_sec`** (default `300`), and while a question is
  waiting every other brokered command on the host is refused. Only the literal answer the prompt names approves;
  silence is a refusal.
- **The fleet's host keys are pinned system-wide**, in `faramir_fleet_known_hosts_path`
  (`/etc/ssh/ssh_known_hosts`), the executor having no `known_hosts` of its own. Each entry is keyed by the name
  ssh looks it up under, `faramir_fleet_known_hosts_name`: the bare address on port 22, `[host]:port` otherwise. A
  key that stops matching fails the play rather than being rewritten.

## What the role adds

`faramir init` establishes the accounts, age key, `.sops.yaml`, SSH identity, directories, config and units. On top
of that, the role:

- Installs sops from its own release `.deb`, the keeper execing it rather than linking it. No age package: sops
  links the library, and `faramir init` mints the keypair
- Downloads the binary from the release named by `faramir_release_tag` (default `dev`, the rolling release CI
  re-cuts on every push to faramir's main), verified against `checksums.txt` from the same release. A version tag
  pins it, provided that tag carries the CLI the [entry commands](#blocked-paths-and-linked-secrets) need. The tag
  is named rather than resolved through the API: `dev` is published with `make_latest=false`, so
  `/releases/latest` never returns it
- On the controller only: runs `faramir init-project` against `playbook_dir`, writes the block covering how to run
  these playbooks through the broker, and prints the public key the next play distributes
- Converges the two block lists and `faramir_links`, the [config entries](#blocked-paths-and-linked-secrets)
  that name a file rather than hold a value
- Pins `kernel.yama.ptrace_scope` to `faramir_ptrace_scope` (default `1`) in
  `/etc/sysctl.d/60-faramir-ptrace.conf`, so one brokered command cannot ptrace another and read the values
  injected into it. `~` leaves the host's value alone
- Runs `faramir doctor` and asserts on its report

Enrol another tree with `cd <dir> && sudo faramir init-project`.

## Blocked paths and linked secrets

**faramir compiles in no credential rules.** What an install refuses by default is its own directories at their
real paths: the config dir, the store, `/var/log/faramir`, `/usr/local/libexec/faramir`, and the service accounts'
state dirs. Everything else on a host is covered because the lists here declare it, and nothing reports what is
missing, so a gap is found by sweeping a host rather than by asking one. `tasks/entries.yml` converges the two.

| List | Entry | Reaches | Checked against the host |
| --- | --- | --- | --- |
| `faramir_blocked_home_paths` | `path` | the agent's file tools and its shell | no, and a rule for a path that is not there holds when it appears |
| `faramir_blocked_commands` | `command` | the agent's shell and a brokered command, a command being neither a file nor a path | no |

- **One list of shapes, declared under every home on the host.** An entry is relative to a home, and
  `vars/main.yml` joins it to the operator's and to each in `faramir_shared_user_homes`, so a store named once is
  refused wherever it turns up. 85 shapes and one other account is 170 declared paths per host, most of them
  absent.
- **Another account's stores are declared on every faramir host, not just the one holding the account.** A rule
  refuses a command that names the path, and the agent works from the controller, where
  `ssh <host> sudo cat <path>` reaches a second account's files over a NOPASSWD sudo that no local file mode
  answers for. `faramir_shared_user_homes` is empty in the defaults and set in `group_vars/faramir.yml`, an
  account name being inventory data, and the role asserts it is a list of absolute homes before anything is
  written: a bare string would otherwise be joined one character at a time.
- **The finer shape wins where a home holds a store and a readable file beside it.** `.ssh/id_rsa` and its five
  siblings rather than `.ssh/`, because the operator's `config` and `known_hosts` are files an agent opens; the
  same for each editor's `User/globalStorage` against its settings and MCP config, and for an agent's token
  against its instruction file. Nothing can except a file from a directory rule, so the cost falls on the other
  accounts, where a key named outside the list is not covered. Name it here rather than blocking the directory
  under one home and the files under another.

- **The agent is refused a declared path named at all**, whatever it meant to do with it, so `ls`, `stat`, `chmod`
  and a sentence quoting the path in an `echo` are refused alike, across its file tools and its shell. The guard
  holds no list of verbs: a verb list leaves any tool not on it unrefused. The entry's strictness does not enter
  into this. Declaring a file also refuses a shell pattern in its directory that could reach it: with `~/.npmrc`
  declared, a glob over the home directory is refused and `ls ~/*.md` is not. Nothing expands the pattern; the
  literal parts are compared against the declared name.
- **The path entries and `faramir_links` are written `--strict`; `faramir_blocked_commands` is not.** The
  flag reaches the brokered route alone, and there only what a command does to the file where it stands. Reading a
  declared file and moving it with `mv` or `ln` are refused either way, a mover leaving the contents readable
  under a name no rule was written for. What `--strict` adds is refusing `chmod`, `chown`, `rm`, `truncate` and a
  redirect over the file, and refusing a command that uses the credential in place (`cryptsetup --key-file`,
  `ssh -i`, `restic --password-file`), which is otherwise the point of the brokered route. The cost is that
  nothing converges such a file through a brokered command: rotating a key or fixing a mode is the operator's at a
  terminal. A command entry cannot carry the flag at all, faramir refusing the pair, a command entry already being
  about what a command does.

- **A path is the only form that names a file, and it is absolute.** Nothing matches a suffix, a prefix, or the
  tail of a path, so a store with no fixed location cannot be declared, and neither can a file an agent opens
  inside a container, where the path is the mount point's and not the host's. What that leaves uncovered on this
  fleet is listed in `defaults/main.yml` beside the paths.
- **A command is literal words, not a pattern.** The space between them matches any run of whitespace and nothing
  else is special. An alternation is spelled out as separate entries.
- **A command entry matches where a command starts**: the beginning of a line, after a separator, or behind a
  prefix that runs something else (`sudo`, `env`, a `VAR=value` assignment). So a bare word covers every use of a
  tool and not the same word inside a flag or a path argument, and a spelled-out subcommand narrows it to that one
  use.

| | a block entry | `faramir_links` |
| --- | --- | --- |
| Entry | `[[secret.block]]` | `[[secret.link]]` |
| Names | a path or a command | a ref, a path, a type, and a key for the types that select |
| Blocked to the agent's file tools | yes, except a command | yes |
| Regrouped, so a brokered command is refused it | no, the mode is left alone | yes |
| In the redactor, tokenised wherever it appears | no, the file is never opened | yes |
| Injectable by ref | no | yes |

- **A block reaches the agent's file tools and its shell**, so a path entry refuses both `Read` and `cat`. A
  command entry reaches a brokered command as well, which `block ls` reports for each one: refused to the agent's
  shell and to a brokered command alike. What a brokered command may do to a declared path is the `--strict`
  question above.
- **Reserve a link for a file its owning tool rewrites in place.** A linked file that is there and will not read
  leaves the broker refusing `run` and `redact` for every ref until it is fixed, and a tool that rewrites its own
  file by rename takes the broker's read with it: `make faramir` grants it again, and between runs the agent has no
  broker at all. Block the file instead where nothing asks for the value by name.
- **A linked path keeps its shape, and the host holding the link declares it once.** A link renders the same rule
  and three things besides, so on that host the block entry adds nothing and gives a refusal two removals, neither
  of which lifts it alone. The shape is not what comes out: `vars/main.yml` subtracts the paths a host's own links
  name, so `~/.npmrc` stays blocked on a `dev` host that has npm and no link, and is a link where there is one.
  The link is the entry that stays, having the ref the value is asked for by.
- **`faramir_links` is set in `host_vars`, not here.** `link add` refuses a new entry whose file is not there, so a
  link in the committed defaults fails the run on a controller without that file. An absent blocked path is
  written and warned about, so those stay in defaults.
- **A shape is relative to a home and in its shortest form**, joined to each home and then matched as written; no
  leading slash and no `~`, which nothing expands. A directory blocks everything under it, whether or not it is
  one on the day the rule is written. The run prints what each entry warned about.
- **Every blocked path is configured, whether or not the host has the file.** faramir writes the rule for an
  absent path and it holds when the file appears, so a tool signed in after a converge is covered before the next
  one runs. The run warns for each path that is not there, and a path spelled wrong warns the same way, so read
  the warnings against the list rather than as noise. What earns an entry is not presence but producibility: a
  host here has the tool that writes the file, or a role installs it. A store nothing on this fleet can produce is
  left out, and adding the tool adds its path.
- **Both commands are idempotent**, so the role names every entry on every run rather than diffing the install: an
  entry already carried is re-applied, which is what puts back a grant a tool took away and a rule an agent's
  settings dropped. `faramir init` re-asserts them all from `config.toml` afterwards.
- **They need a current faramir**, which `faramir_release_tag: dev` tracks: the `block` subcommand, a flag per form
  with no default, `--json` on each, `--declared` on `block ls`, `--strict` on `block add` and `link add` under
  that name rather than `--any-mention`, and no `--config-dir` on any of them but `init`.
  An older tag fails with cobra's unknown-flag error, except for two that fail quietly: an add that leaves its
  entry to the next `init`, and a build that still takes `--config-dir`, which without one falls through to
  `/etc/faramir` and configures an install this host does not have.
- **They run before the enrolment**, which is what renders the entries into this tree's agent files. Only the
  account-wide rule files are an add's own to write, and pi's rules live in its per-tree extension alone.
- **The block entries converge both ways.** A run adds what the two lists name and removes every declared entry
  they do not, reading the host's own with `block ls --declared` and comparing per form, the form being part of
  what identifies an entry. So the listing and `defaults/main.yml` agree once a run finishes, and an entry added
  on a host by hand does not survive one. The run asserts that every `kind` it reads back is one of the two, a
  third being one it would compare against no list and leave standing.
- **A removal takes its rendered rules with it.** `block rm` re-renders the agent rule files as `block add` does,
  and faramir keeps a record of what it last wrote into each one (`written-rules.json`, beside the config), so a
  rule it rendered and no longer renders comes out while one nobody recorded is left as the operator's. A rule
  written before that record existed is in the second class until a later run re-records it. The run names what it
  removed.
- **`faramir_links` is adds only.** A link grants the broker read and regroups the file, so dropping one changes
  what the host can serve rather than bringing a list back into agreement. Take an entry out of `faramir_links`
  and run the `rm` yourself. `link rm` takes no `--strict`, an entry coming out whichever strictness it carried.

## Agents

`faramir_agents` names every agent the [dev role](../dev/README.md) installs that faramir can configure, and the
same list goes to `init` and to `init-project`. Named rather than left to faramir's `auto`, which reaches an agent
only after it has run here once unguarded.

| Agent | In this tree | In the operator's home | Redaction |
| --- | --- | --- | --- |
| claude | `PreToolUse` hook and deny rules in `.claude/settings.local.json`, MCP server in `.mcp.json` | deny rules in `.claude/settings.json`, a credentials section in `.claude/CLAUDE.md` | full |
| codex | `PreToolUse` hook in `.codex/hooks.json`, which routes; credentials section in `AGENTS.md` | a deny-only `PreToolUse` hook in `.codex/hooks.json`, a credentials section in `.codex/AGENTS.md` | full |
| opencode | plugin in `.opencode/plugins/`, MCP server in `opencode.json` | deny rules in `.config/opencode/opencode.json`, a credentials section in `.config/opencode/AGENTS.md` | full |
| kilocode | plugin in `.kilo/plugin/`, MCP server in `kilo.json` | deny rules in `.config/kilo/kilo.json`, a credentials section in `.kilocode/rules/faramir.md` | full |
| pi | extension in `.pi/extensions/`, which carries the deny rules | a credentials section in `.pi/agent/AGENTS.md`, and no deny rules: the extension is where pi reads them | full |
| antigravity | MCP server in `.agents/mcp_config.json`, credentials section in `.agents/rules/faramir.md` | a credentials section in `.gemini/GEMINI.md`, and no deny rules | none |

- **Antigravity is partial support.** Its hooks decide and cannot rewrite a tool call, so nothing routes what it
  runs through the broker and nothing redacts what comes back. It gets the MCP tools and the instructions to use
  them, and every enrolment warns as much.
- **Codex has no rule file, so its hook is the whole of what refuses it a path.** Its own `.rules` files are an
  exec policy, which decides commands and names none, so the hook matches every tool rather than Bash alone.
  It also runs no hook it has not been told to trust and says nothing when it skips one, so an enrolment does
  nothing until Codex has been started once and the hook trusted; and it must run without its own sandbox.
- **Cursor is installed here and faramir does not configure it**, so a credential a command of its prints
  reaches the model.
- Enrolling claude or codex gives up this project's Bash prompts: a rewritten command matches no permission
  rule, so the hook approves it, and that approval covers every command the deny list does not name. The
  other four have no approval to return.
- Nothing an enrolment writes into a tree is committed: this repo's `.gitignore` covers `.claude/*` and the
  agents' instruction filenames, and the operator's global ignore covers the rest.

## Verification

From the repository root: an ad-hoc `ansible` command has no playbook, so the vars plugin looks for
`faramir.env` in the working directory, and run from anywhere else it fails naming the missing file.

```bash
faramir run --env-file faramir.env -- \
    ansible <host> -m debug -a 'var=msmtp_password'
# -> "msmtp_password": "«SECRET:msmtp_password»"
```

| Output | Meaning |
| --- | --- |
| `«SECRET:...»` | the chain works end to end |
| `VARIABLE IS NOT DEFINED!` | the ref was not injected |
| `ENC[AES256_GCM,...]` | the encrypted file sits where Ansible auto-loads it |

`sudo faramir doctor` adds the boundary checks, which ask each account what it can reach and need a uid other than
your own.
