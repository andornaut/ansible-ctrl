# faramir

Installs the [faramir](https://github.com/andornaut/faramir) secret broker, so a coding agent works on a host
without being able to read the credentials kept there. What it protects against, and its accounts, units, config
model and store, are in faramir's own [README](https://github.com/andornaut/faramir#readme); this covers what is
specific to this repo.

Two kinds of install, from one role:

| | Controller | Every other faramir host |
| --- | --- | --- |
| Inventory | in `faramir_controller` and in `faramir` | in `faramir` |
| Refused paths, linked secrets, redaction | yes | yes |
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

- **`sudo make faramir` is refused.** A root run connects with the broker's key rather than your `~/.ssh`, so it
  needs a fleet that already accepts that key: not the first install, not a rotated key, and not a host added or
  rebuilt since the last run. `ALLOW_ROOT=1` skips the refusal.
- Preflight drops an unreachable host here as it does everywhere else, and a dropped host keeps whatever it
  already authorized. Re-run `make faramir` once it is back up, and after generating a new key run it with every
  host reachable.

`faramir.yml` applies the role's two entry points in order:

| Play | Entry point | Hosts | Effect |
| --- | --- | --- | --- |
| first | `tasks/broker.yml` (via `tasks/main.yml`) | `faramir` | Installs the broker on each of them |
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

Which home those paths resolve under is `FARAMIR_OPERATOR` where the broker sets it, and `SUDO_USER` otherwise.
Each covers what the other gets wrong: `SUDO_USER` is the operator wherever a human typed the sudo, and the
executor account on a brokered run, which is the one `FARAMIR_OPERATOR` answers. A host whose faramir predates
that variable resolves the executor and refuses the run, naming the home it looked in; `make faramir` fixes it.

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
  `faramir-exec`, which has no sudo here. Apply the controller's own playbooks as the operator.
- **`faramir_allow_sudo` needs the original `sudo`.** Ubuntu 26.04 ships `sudo-rs`, which does not implement
  `pam_service`; the grant names it, so `visudo` rejects the whole file and the install refuses. It removes the
  file again rather than leaving a broken entry, so the host's own `sudo` is unaffected and one left without the
  grant refuses every escalation. Everything else works there.
- **An escalation expires after `faramir_escalation_timeout_sec`** (default `300`), and while a question is
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
  re-cuts on every push to faramir's main), verified against `checksums.txt` from the same release. Set it to a
  version tag (`v0.5.0`) to pin. The tag is named rather than resolved through the API: `dev` is published with
  `make_latest=false`, so `/releases/latest` never returns it
- On the controller only: runs `faramir init-project` against `playbook_dir`, writes the block covering how to run
  these playbooks through the broker, and prints the public key the next play distributes
- Converges `faramir_refused_paths` and `faramir_links`, the two [config entries](#refused-paths-and-linked-secrets)
  that name a file rather than hold a value
- Pins `kernel.yama.ptrace_scope` to `faramir_ptrace_scope` (default `1`) in
  `/etc/sysctl.d/60-faramir-ptrace.conf`, so one brokered command cannot ptrace another and read the values
  injected into it. `~` leaves the host's value alone
- Runs `faramir doctor` and asserts on its report

Enrol another tree with `cd <dir> && sudo faramir init-project`.

## Refused paths and linked secrets

`faramir init --agent` writes deny rules against key material by name and suffix: `id_rsa` and its kind, `*.key`,
`*.pem`, a `credentials` path component, `.env*` dotfiles, sops and vault files, and the sops, age and faramir
directories. The two lists here name what those miss, and `tasks/entries.yml` converges them.

| | `faramir_refused_paths` | `faramir_links` |
| --- | --- | --- |
| Entry | `[[secret.refuse]]` | `[[secret.link]]` |
| Names | a path | a ref, a path, a type, and a key for the types that select |
| Refused to the agent's file tools | yes | yes |
| Regrouped, so a brokered command is refused it | no, the mode is left alone | yes |
| In the redactor, tokenised wherever it appears | no, the file is never opened | yes |
| Injectable by ref | no | yes |

- **A refusal stops the agent's file tools and nothing else.** A brokered command whose mode allows it may still
  read a refused file and print it in the clear.
- **Reserve a link for a file its owning tool rewrites in place.** A linked file that is there and will not read
  leaves the broker refusing `run` and `redact` for every ref until it is fixed, and a tool that rewrites its own
  file by rename takes the broker's read with it: `make faramir` grants it again, and between runs the agent has no
  broker at all. Refuse the file instead where nothing asks for the value by name.
- **A linked path does not also go in `faramir_refused_paths`.** A link renders the same rule and three things
  besides, so the second entry adds nothing and faramir says so.
- **`faramir_links` is set in `host_vars`, not here.** `link add` refuses a new entry whose file is not there, so a
  link in the committed defaults fails the run on a controller without that file. An absent refused path is
  skipped and named, so those stay in defaults.
- **A path is absolute and in its shortest form**, a rule matching it as written; no `~`, which nothing expands. A
  directory refuses everything under it, whether or not it is one on the day the rule is written. The run prints
  what each entry warned about.
- **Only a refused path the controller has is configured.** The role stats each one as root and names the rest in
  its output rather than refusing them, an entry naming a path no host here carries being one nothing can check.
  A file that appears after a run is refused by the next one and not before.
- **Both commands are idempotent**, so the role names every entry it configures on every run rather than diffing
  the install: an entry already carried is re-applied, which is what puts back a grant a tool took away and a rule
  an agent's settings dropped. The only state read first is whether a refused path is there. `faramir init`
  re-asserts them all from `config.toml` after that, so an entry an earlier run wrote holds whatever became of the
  file.
- **They need a faramir carrying `--json` on `refuse add` and `link add`**, which `faramir_release_tag: dev` does.
  A tag pinned to a version older than that fails these tasks with cobra's unknown-flag error.
- **They run before the enrolment**, which is what renders the entries into this tree's agent files. Only the
  account-wide rule files are an add's own to write, and pi's rules live in its per-tree extension alone.
- **Removal is by hand.** `faramir refuse rm` and `faramir link rm` drop the entry but cannot take the rule out of
  an agent's settings, those files being merged rather than replaced, so the role only ever adds. Take an entry out
  of the list here and run the `rm` yourself.

## Agents

`faramir_agents` names every agent the [dev role](../dev/README.md) installs that faramir can configure, and the
same list goes to `init` and to `init-project`. Named rather than left to faramir's `auto`, which reaches an agent
only after it has run here once unguarded.

| Agent | In this tree | In the operator's home | Redaction |
| --- | --- | --- | --- |
| claude | `PreToolUse` hook and deny rules in `.claude/settings.json`, MCP server in `.mcp.json` | deny rules and a credentials section, both under `.claude/` | full |
| opencode | plugin in `.opencode/plugins/`, MCP server in `opencode.json` | `.config/opencode/` | full |
| kilocode | plugin in `.kilo/plugin/`, MCP server in `kilo.json` | `.config/kilo/kilo.json`, `.kilocode/rules/faramir.md` | full |
| pi | extension in `.pi/extensions/`, which carries the deny rules | `.pi/agent/` | full |
| antigravity | MCP server in `.agents/mcp_config.json`, credentials section in `.agents/rules/faramir.md` | `.gemini/` | none |

- **Antigravity is partial support.** Its hooks decide and cannot rewrite a tool call, so nothing routes what it
  runs through the broker and nothing redacts what comes back. It gets the MCP tools and the instructions to use
  them, and every enrolment warns as much.
- **Codex and Cursor are installed here and faramir configures neither**, so a credential a command of theirs
  prints reaches the model.
- Enrolling claude gives up this project's Bash prompts: a rewritten command matches no permission rule, so the
  hook approves it. The other four have no approval to return.
- The files an enrolment writes into a tree are gitignored globally rather than by this repo.

## Verification

From the repository root: an ad-hoc `ansible` command has no playbook, so the vars plugin looks for
`faramir.env` in the working directory, and run from anywhere else it reports the credential undefined.

```bash
faramir run --env-file faramir.env -- \
    ansible <host> -m debug -a 'var=msmtp_password'
# -> "msmtp_password": "«SECRET:msmtp_password»"
```

| Output | Meaning |
| --- | --- |
| `«SECRET:...»` | the chain works end to end |
| a bare name | the ref was not injected |
| `ENC[AES256_GCM,...]` | the encrypted file sits where Ansible auto-loads it |

`sudo faramir doctor` adds the boundary checks, which ask each account what it can reach and need a uid other than
your own.
