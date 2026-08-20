# faramir

Installs the [faramir](https://github.com/andornaut/faramir) secret broker on the Ansible controller, so a coding
agent can run playbooks against the fleet without being able to read the credentials they use. What it protects
against, and its accounts, units, config model and store, are in faramir's own
[README](https://github.com/andornaut/faramir#readme); this covers what is specific to this repo.

## Usage

```bash
make faramir    # install the broker, then authorize its key on the fleet
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
| first | `tasks/broker.yml` (via `tasks/main.yml`) | `faramir` | Installs the broker on the controller |
| second | `tasks/ssh.yml` (`tasks_from`) | `all` | Authorizes the broker's key and NOPASSWD sudo, pins the fleet's host keys in `faramir_fleet_known_hosts_path`, then pings the hosts it still holds back through the broker |

`faramir_controller` is the one host it may install on, derived from the `faramir` group rather than named here,
this repo being public: `broker.yml` refuses to run anywhere else, and `ssh.yml`
requires the `faramir` group to hold that host and no other.

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
faramir run --env-file faramir.env -- ansible-playbook <playbook>.yml --limit '!faramir'
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
- **Every credential lives in the store**, `~/.config/faramir/secrets/ansible-ctrl.sops.yml`. One held anywhere
  else is neither injectable through `--env` nor known to the redactor.
- **The store must not sit under `group_vars/` or `host_vars/`**, where Ansible auto-loads every `.yml`: a sops
  file is valid YAML, so each var binds to its `ENC[...]` ciphertext and hosts get the ciphertext as the password.
  Nor in the checkout, this repo being public. `faramir init` refuses both.
- **A brokered run reaches the fleet, not the controller**, hence `--limit '!faramir'`: commands run as
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

- Downloads the binary from the release named by `faramir_release_tag` (default `dev`, the rolling release CI
  re-cuts on every push to faramir's main), verified against `checksums.txt` from the same release. Set it to a
  version tag (`v0.5.0`) to pin. The tag is named rather than resolved through the API: `dev` is published with
  `make_latest=false`, so `/releases/latest` never returns it
- Runs `faramir init-project` against `playbook_dir`, and writes the block covering how to run these playbooks
  through the broker
- Pins `kernel.yama.ptrace_scope` to `faramir_ptrace_scope` (default `1`) in
  `/etc/sysctl.d/60-faramir-ptrace.conf`, so one brokered command cannot ptrace another and read the values
  injected into it. `~` leaves the host's value alone
- Runs `faramir doctor` and asserts on its report

Enrol another tree with `cd <dir> && sudo faramir init-project`.

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
