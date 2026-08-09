# faramir

Installs the [faramir](https://github.com/andornaut/faramir) secret broker on the Ansible controller, so a coding agent can run playbooks against the fleet without being able to read the credentials they use.

## Usage

```bash
make faramir                     # install and reconcile the broker on the controller
make faramir_fleet ASK_PASS=1    # authorize the broker's key on the managed hosts
```

Both are operator actions. `faramir.yml` applies this role to the `faramir` inventory group and no other play reaches it: a brokered run would rewrite its own confinement as root and kill the command doing the rewriting.

## Layout

| Path | Mode | Contents |
| --- | --- | --- |
| `~/.faramir/config.toml` | `0644 root` | faramir's own, rewritten by `init` on every run, carrying `[ssh] keys` from `faramir_broker_ssh_key`. Do not edit it. |
| `~/.faramir/config.d/ansible-ctrl.toml` | `0644 root` | `[secrets] files`, written by this role every run |
| `~/.faramir/age.key` | `0400 faramir-keeper` | decrypts the store; the operator can unlink it but not read it. |
| `~/.faramir/secrets/` | `2750 root:faramir-keeper` | the keeper's own group, and the keeper is the only account that opens one of these files; neither the operator nor the broker is in it, so reading or editing a managed file needs sudo. |
| `~/.faramir/secrets/ansible-ctrl.sops.yml` | | every credential this repo uses |
| `/var/lib/faramir-broker/.ssh/id_ed25519` | broker | the key the broker lends to brokered commands |

Config and store both sit in the operator's encrypted home, so a powered-off disk carries neither the ciphertext nor the key that opens it. Point `faramir_config_dir` at an unencrypted filesystem and that no longer holds.

Drop-ins merge over the base in lexical order and face every check the base file does, so a typo is a hard error naming the alternatives. `faramir status` reports `configs`: the base file plus every drop-in that contributed. Neither daemon re-reads its config while running, so the role runs `faramir reload`.

## Constraints

- **Every credential lives in the store.** The keeper decrypts sops and nothing else, so a credential held anywhere else is absent from its value set: neither injectable through `--env` nor known to the redactor. A playbook that prints such a value prints it in plaintext.
- **The store must never sit under `group_vars/` or `host_vars/`.** Ansible auto-loads every `.yml` there and a sops file is valid YAML, so each var binds to its `ENC[...]` ciphertext. Nothing errors; hosts get the ciphertext as the password. `faramir init` refuses to finish against a store under either directory.
- **The store must not be in the checkout.** This is a public repo, and a store inside it is ciphertext of every credential one `git add -f` from publication.
- **No sudo password in the store.** `ansible_become_password` for the operator is their login password, and the agent already runs as that account: with the password it has sudo, on the controller that is root, and root reads the keeper's age key. The fleet gets NOPASSWD sudo instead, installed by `faramir_fleet.yml`.
- **A brokered run reaches the fleet, not the controller.** Commands run as `faramir-exec`, which has no sudo, hence `--limit '!faramir'`. Granting that uid sudo here would hand the agent root on the machine holding the age key. Apply the controller's own playbooks as the operator.
- **The keeper cannot see the rest of the home.** Its unit carries `ProtectHome=tmpfs` plus `BindReadOnlyPaths` of `faramir_config_dir` alone, rendered by `init` in the unit rather than a drop-in. Move `faramir_secrets_dir` outside the config dir and init emits a second bind for it.
- **Nothing under the home is readable before first login.** A reboot leaves the store absent and a 03:00 renewal on an unmounted home does not run. The bind carries no leading `-`, so the keeper fails to start rather than coming up empty, and an absent `[secrets]` file counts as a load failure so `--check` fails too.
- **Group membership is read at login.** Log out and back in before `dev` takes effect.
- **`faramir_dev_group` grants traversal of the operator's home**, through ordinary group ownership, so keep it to the accounts that need it. It is not the store's group.
- **The config directory is root's, wherever it sits.** `config.d/*.toml` merges over `config.toml` and `[exec.base_env]` merges key by key, so whoever can write a drop-in chooses the `PATH` a brokered command's child runs with, holding the requested secret. Editing config by hand needs sudo, the same as editing the store.
- **The operator cannot read the store.** `sops -d` and `sops exec-env` fail for want of a readable file, whatever age identities are listed as recipients. `sudo faramir edit <file>` is the way in; it decrypts to a 0600 file in a root-owned tmpfs and re-encrypts to the recipients the file already had.

## Running playbooks

`homeautomation`, `msmtp` and `webservers` read a credential and re-enter under `sops exec-env`. The other twelve targets run straight through.

| Run | Command |
| --- | --- |
| no credential | `make <playbook>` |
| credential, controller | `sudo make <playbook> -- --limit <controller>` |
| credential, fleet | `faramir run --env-file faramir.env -- ansible-playbook <playbook>.yml --limit '!faramir'` |

The re-entry succeeds only as root, the store's group holding no human, and neither account covers the whole fleet: root has no key for a host it must reach over ssh, and the executor has no sudo on the controller. `make` refuses a run it cannot serve and prints both commands.

`faramir.env` holds refs, never values. Both paths set the same variable names, so one list serves both.

`--ask-become-pass` is added only when the run reaches the controller, decided per run by one ansible call that connects to nothing. Roles are checked as well as hosts, because `delegate_to: localhost` reaches the controller without appearing in any host list. It errs toward asking, and a run already root is never asked. `ASK_PASS=1` forces it, which `faramir_fleet.yml` needs: that is the run establishing the NOPASSWD which makes prompting unnecessary.

## What the role does

`faramir init`, run once as root with this project's paths, establishes the accounts and the `dev` group, the age key, `.sops.yaml`, the broker's SSH identity, the directories, the binaries, the hook, the config, the units and their sandboxing, and the sockets. None of that is restated in the role. `init` reports per step in JSON, so `changed_when` reads a field; under `--check` the role passes `--dry-run`, which computes every answer and writes nothing.

What belongs to this project rather than to faramir:

| Step | Why it is here |
| --- | --- |
| `faramir init-project` against `playbook_dir` | which tree the agent works in is this repo's to say |
| the `config.d/ansible-ctrl.toml` drop-in | which sops files the broker manages is this repo's, and faramir ships no list |
| `faramir reload` when that changes | the drop-in is the role's to write, so triggering the daemons is the role's too |
| the `AGENTS.md` block | how to run *these* playbooks through the broker |
| `faramir doctor` and its assert | the run has to fail when the result does not work, and a playbook is what fails |

### The binary

One executable. The daemons, the MCP server and the PreToolUse hook are subcommands (`faramir broker`, `keeper`, `exec`, `mcp`, `guard`), separated by the `User=` each unit runs its subcommand as. Units, base config, agent hook and docs are embedded in it; `/usr/local/libexec/faramir/` holds the hook's deny list and wrap script, rendered per install.

faramir's CI cuts a `dev` release on every push to its `main`: one `faramir_linux_{arch}.tar.gz` per architecture plus `checksums.txt`, laid out as goreleaser names a tagged release. The role downloads the archive into a temp directory, unpacks it, hands the directory to `init`, and removes it. One ~7MB archive a run, no Go toolchain and no faramir checkout on the controller.

`get_url` verifies against `checksums.txt` from the same release. `dev` is deleted and re-cut on every push, so a download straddling a re-cut fails the checksum rather than installing a build that was never verified.

`faramir_arch` maps the kernel name onto the asset's: `x86_64` stays, `aarch64` becomes `arm64`. The kernel is not mapped: faramir is linux-only.

### The working tree

Brokered commands run in the checkout the play was run from, `playbook_dir`. No variable names it, and the role checks that the tree exists on the target before installing anything.

`faramir init-project` group-owns that tree, sets the setgid bits, and makes every directory group-executable from the home down, so `faramir-exec` and the operator stop fighting over each other's files. Not `chmod o+x`, which under `umask 002` would open the whole home rather than a path through it. It also registers the `PreToolUse` hook in `.claude/settings.json`, writes `.mcp.json`, splices faramir's credentials block into `AGENTS.md`, and reads the shared group out of the installed config.

Enrol another tree with `cd <dir> && sudo faramir init-project`, which defaults to where you are standing. Nothing the broker reads names a tree: file modes plus `ProtectSystem=strict` are what keep brokered commands out of everything else.

### The broker's SSH identity

The broker holds the key under its own uid, loads it into an `ssh-agent` it owns, and passes the child only `SSH_AUTH_SOCK`, so `faramir-exec` can authenticate with a key it cannot read. `init` generates the key when missing, then asks the running broker what its agent holds and fails when it holds nothing. `doctor` reports the same as a warning.

The public half opens nothing until `faramir_fleet.yml` puts it in `authorized_keys`. `faramir_fleet.yml` reads the key off the controller, installs it on every host except the controller (without `exclusive`, so existing keys keep working), grants that account NOPASSWD sudo, then pings every host *through the broker*.

## Verification

```bash
faramir run --env-file faramir.env -- \
    ansible <host> -m debug -a 'var=secret_msmtp_password'
# -> "secret_msmtp_password": "«SECRET:secret_msmtp_password»"
```

| Output | Meaning |
| --- | --- |
| `«SECRET:...»` | the chain works end to end |
| a bare name | the ref was not injected |
| `ENC[AES256_GCM,...]` | the encrypted file sits where Ansible auto-loads it |

A broker whose secrets file it cannot read comes up healthy and protects nothing, so the role fails when a managed sops file exists and yielded no refs. `faramir doctor` reports what the broker loaded. `faramir run -- ssh-add -l` asks what a brokered command actually gets.

faramir also ships a verification matrix that runs against the live install. It needs a checkout, which the role does not install:

```bash
git clone git@github.com:andornaut/faramir.git && cd faramir && sudo tests/verify.sh
```

## Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `faramir_user` | `primary_user` | Owns the working tree and the config. Never the agent. |
| `faramir_dev_group` | `dev` | Shared access to the working tree. |
| `faramir_broker_user` | `faramir-broker` | Policy, redaction, audit log, SSH keys. |
| `faramir_keeper_user` | `faramir-keeper` | Holds the age key; execs nothing but sops. |
| `faramir_exec_user` | `faramir-exec` | Forks brokered commands; holds nothing. |
| `faramir_project_hook` | `true` | Register the `PreToolUse` hook in the checkout. Redacts everything the agent runs here, and auto-approves Bash here as a consequence. |
| `faramir_config_dir` | `{{ faramir_user_home }}/.faramir` | Where `config.toml`, `config.d/` and the age key live. |
| `faramir_secrets_dir` | `{{ faramir_config_dir }}/secrets` | Where the store lives. |
| `faramir_secrets_files` | `[{{ faramir_secrets_dir }}/ansible-ctrl.sops.yml]` | The managed sops files, written to the drop-in every run. |
| `faramir_broker_ssh_key` | `/var/lib/faramir-broker/.ssh/id_ed25519` | The key the broker lends, generated when missing. Empty leaves `[ssh] keys` unset. |
| `faramir_operator_age_key` | `{{ faramir_user_home }}/.config/sops/age/keys.txt` | The operator's own age identity, minted when missing and added to `.sops.yaml` as a second recipient. Empty leaves the keeper as the only one. |
| `faramir_install_agent_config` | `true` | Install faramir's `Read` deny rules into the operator's Claude settings. |
| `faramir_fleet_authorize_key` | `true` | Whether `faramir_fleet.yml` adds or removes the broker's key. |

Service account names and `faramir_dev_group` are free to change here; `init` renders both the config and the units from the same values.

`config.toml` is faramir's own and `init` rewrites it every run, so nothing here edits it and an edit made by hand is replaced. Settings that belong to this repo go in the `config.d/ansible-ctrl.toml` drop-in, which `init` never touches; anything else you want to set goes in a drop-in of your own beside it.
