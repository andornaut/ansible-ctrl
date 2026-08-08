# faramir

Installs the [faramir](https://github.com/andornaut/faramir) secret broker on the
Ansible controller, so a coding agent can run playbooks against the fleet without
being able to read the credentials they use.

Run it with `make faramir`.

## Why its own playbook

The role writes the systemd units, the broker config and the filesystem
permissions that confine the agent, then restarts the broker. A brokered run
reaching those tasks would rewrite its own confinement as root and kill the
command doing the rewriting. So the role is applied by `faramir.yml` to a
`faramir` inventory group and is reachable from no other play.

Installing faramir is an operator action; brokering playbooks is an agent action
run later. Ansible never needs faramir in order to run.

## Where the credentials have to be

The keeper decrypts sops and nothing else. A credential held anywhere else is
absent from the keeper's value set, so it is neither injectable through `--env`
nor known to the redactor: a playbook that prints it prints it in plaintext.
Every credential therefore lives in `~/.faramir/secrets/ansible-ctrl.sops.yml`,
`vars_plugins/secret_env.py` turns each injected `secret_*` variable into one of
the same name, and `host_vars/` refers to the names.

The store is the only part of faramir that lives in the operator's home, and it
is the only part that can. The agent runs as that account and its age identity is
in that home, so it can already decrypt the ciphertext wherever it sits: moving
the file costs nothing. Everything else is what stops the agent, and a file in
the agent's own home is a file it can rewrite. `config.toml` is the policy
itself, the sealed age credential is `0400 root:root` so the account cannot swap
it, the units define the three service uids, and the binaries are what enforce
any of it. Those stay outside every home.

Not in the checkout either: it is a public repo, so a store inside it is
ciphertext of every credential one `git add -f` from publication.

`faramir_secrets_dir` is created `2770 root:dev`, so `sops` edits it in place
through the group without sudo and the keeper can read what lands there. Root
owns the directory rather than the operator: group write is all either of them
needs to edit a file in it, and owning it would additionally let the operator
change its mode, which is the one thing keeping the keeper's access from being
revoked by accident.

The keeper reaches it through its own unit, which `faramir init` renders with
these lines whenever the config or the store is inside a home:

```ini
[Service]
ProtectHome=tmpfs
BindReadOnlyPaths=/home/<operator>/.faramir
```

`tmpfs` rather than dropping `ProtectHome`: every other home stays invisible to
the process holding the age key, and only that one directory is bound back in.
`faramir_secrets_dir` sits inside `faramir_config_dir`, so the single bind covers
both; move it outside and init emits a bind of its own for it.

In the unit rather than a drop-in, which is why nothing here writes one. A
sandbox split across two files is one where the second can be stale, or absent,
or written after the run that judged the unit without it.

What that costs: nothing under the home is readable before the operator's first
login, so a reboot leaves the store absent, and a renewal at 03:00 on an unmounted
home does not run. Neither is silent. The bind carries no leading `-`, so the
keeper fails to start rather than coming up empty, and the broker counts an
absent `[secrets]` file as a load failure, so `--check` fails too. `faramir
doctor` and the cron's preflight report the rest.

It must also never sit under `group_vars/` or `host_vars/`. Ansible auto-loads
every `.yml` there and a sops file is valid YAML, so each var would bind to its
`ENC[...]` ciphertext. Nothing errors; hosts get the ciphertext as the password.
`faramir init` refuses to finish against a store under either directory.

A broker whose secrets file it cannot read comes up healthy and protects nothing.
`faramir doctor` reports what the broker loaded, and the role fails when a
managed sops file exists and yielded no refs.

To prove the chain end to end:

```bash
faramir run --env-file faramir.env -- \
    ansible <host> -m debug -a 'var=secret_msmtp_password'
# -> "secret_msmtp_password": "«SECRET:secret_msmtp_password»"
```

Anything else is a fault. A bare name means the ref was not injected;
`ENC[AES256_GCM,...]` means the encrypted file sits where Ansible auto-loads it.

## Running playbooks

`make` is the operator's. It wraps itself in `sops exec-env` when the values are
not already in the environment:

```bash
make homeautomation                      # reaches the controller, so it asks for sudo
make homeautomation -- --limit <host>    # does not, so it does not ask
make faramir_fleet ASK_PASS=1            # forces the prompt
```

Whether it prompts is decided per run by one ansible call that connects to
nothing, from which hosts the run targets, honouring `--limit`, and which roles
it pulls in. The second matters because a role can reach the controller without
targeting it, through `delegate_to: localhost`, which no host list shows.

It errs toward asking: a delegation naming a remote host costs a keystroke, where
not asking costs a half-applied run. `ASK_PASS=1` forces the prompt, which the
fleet play needs because it is the run that establishes the NOPASSWD that makes
prompting unnecessary. A run that is already root is never asked, sudo wanting
nothing from root.

The agent does not use `make`. It calls ansible through the broker:

```bash
faramir run --env-file faramir.env -- \
    ansible-playbook homeautomation.yml --limit '!faramir'
```

`faramir.env` holds refs, never values. Both paths set the same variable names,
so one list serves both.

> [!IMPORTANT]
> A brokered run reaches the fleet, not the controller. Commands run as
> `faramir-exec`, which has no sudo, so a brokered playbook configures the
> managed hosts over SSH and cannot apply a `become` task to the controller,
> which is why `--limit '!faramir'` excludes it. Granting that uid sudo on the
> controller would hand the agent root on the machine holding the age key, which
> is what the arrangement exists to prevent. Apply the controller's own playbooks
> as the operator.

## No become password in the store

The store holds no sudo password, and must not. `ansible_become_password` for the
operator's account is their login password, and the agent already runs as that
account: what it lacks is not the uid but the password, and with it `sudo`. On
the controller that is root, and root reads the keeper's age key. An agent that
extracted the value (the threat model accepts this is possible, since `| rev` and
`| cut` defeat redaction) would turn one leaked credential into every credential,
retroactively.

The rule is that no credential goes in the store whose compromise would defeat
the store. Where the operator's password is the same on the controller and the
fleet, there is no fleet-only become password to store either, so brokered runs
carry none and the fleet gets NOPASSWD sudo instead, installed by
`faramir_fleet.yml` alongside the key.

## What the role does

`faramir` publishes no release binaries, so the role builds them from the
checkout at `faramir_src_dir` with `make build` (Go, from the `dev` role), then
runs `faramir init` once, as root, with this project's paths on the command
line. That one command establishes the accounts and the `dev` group, the age key,
`.sops.yaml`, the broker's SSH identity, the directories, the binaries, the hook,
the config, the systemd units and their sandboxing, the TPM sealing, and the
sockets. None of it is restated here: a setting named in both places is one that
can disagree with itself.

What is left for the role is the part that belongs to this project rather than to
faramir:

| Step | Why it is here and not in faramir |
| --- | --- |
| the `config.d/ansible-ctrl.toml` drop-in | which sops files the broker manages is this repo's, and faramir ships no list of them |
| `faramir reload` when that changes | the drop-in is the role's to write, so getting the daemons onto it is the role's to trigger |
| the `AGENTS.md` block | how to run *these* playbooks through the broker, which faramir's own snippet says nothing about |
| `faramir doctor` and its assert | the run has to fail when the result does not work, and a playbook is what fails |

`init` reports per step in JSON, so `changed_when` reads a field rather than
inferring one from stat-ing the host before and after. Under `--check` the role
passes `--dry-run`, which computes every answer and writes nothing.

The binaries are the only thing that crosses from the checkout: the units, the
base config, the agent hook and the docs are embedded in them, so `init` needs no
source layout and this role knows about none.

## The working tree

`faramir_worktree` is the operator's own checkout of this repo, so there is one
copy of the inventory rather than two to keep in step. Brokered commands run
there, so it has to be reachable by `faramir-exec`, and by nothing else: the
sops files are read from `faramir_secrets_dir`, which the keeper sees through a
bind of that one directory and nothing else of the home around it.

`faramir-exec` is not the operator's uid and a home is 0700, so the role passes
that checkout to `init` as `--share-tree`: it group-owns the tree and sets the
setgid bits, so a brokered command and the operator stop fighting over each
other's files, and makes every directory group-executable from the home down.
Not `chmod o+x`, which with `umask 002` in force would open the whole home rather
than a path through it.

It is named per directory rather than derived, because faramir names no tree
anywhere: a brokered command runs where its caller was. Share another the same
way, `sudo faramir share-tree <dir>`, from anywhere.

The role requires the tree to exist and does not create it: `hosts`, `host_vars/`
and `group_vars/` are gitignored, so a fresh clone parses but has no inventory.

Nothing the broker reads names this tree: neither the systemd units nor the
config. What keeps a brokered command out of everything else is the file mode,
plus `ProtectSystem=strict`, which makes the hierarchy read-only apart from
`/home`.

> [!NOTE]
> Traversal is granted by group ownership, which is ordinary inode metadata and
> so passes through an encrypted home unchanged. The cost is that membership of
> `faramir_dev_group` is also a grant to traverse the operator's home, so keep it
> to the accounts that need it.

## The broker's SSH identity

Brokered commands run as `faramir-exec`, which must be able to use the key that
reaches the fleet without being able to read it. The broker holds the key under
its own uid, loads it into an `ssh-agent` it owns, and passes the child only
`SSH_AUTH_SOCK`.

A broker started without a key logs one warning and carries on: every socket
comes up active, `--check` passes, and every brokered playbook then fails to
reach a single host. `init` generates the key when missing, then asks the running
broker what its agent holds:

```bash
faramir run -- ssh-add -l
```

Asked through the broker rather than read off disk, because what matters is what
a brokered command gets. Both `init` and `faramir doctor` fail when the agent
holds nothing.

Generating the key grants nothing on its own. Its public half has to reach the
managed hosts, which the fleet play below does, and the role prints it at the end
of every run.

Set `faramir_broker_ssh_key=""` to leave `[ssh] keys` empty. The keys then have
to live where the executor's own uid can read them.

## What this project sets, and where

`~/.faramir/config.toml` is faramir's, rendered by `init` from its own template
and never edited here. Both it and the base config leave `[secrets] files` and
`[ssh] keys` empty on purpose, because a value that lands only on a first
install can never be reconciled afterwards. Each is set in a drop-in instead,
and they have different owners:

```toml
# 00-faramir-init.toml -- written by faramir init, every run
[ssh]
keys = ["/var/lib/faramir-broker/.ssh/id_ed25519"]

# ansible-ctrl.toml -- written by this role, every run
[secrets]
files = ["/home/<operator>/.faramir/secrets/ansible-ctrl.sops.yml"]
```

The key is faramir's because faramir generates it; the store is this repo's
because faramir has no opinion about what is in it. Naming either in both places
would put it in the merged list twice.

Drop-ins merge over the base in lexical order and are held to every check the
base file is, so a typo here is a hard error naming the alternatives rather than
a setting that reads as though it took effect. `faramir status` reports
`configs`, the base file and every drop-in that contributed, which is where to
look when a setting is not what you expect.

A drop-in rather than the base config for a specific reason: `init` keeps an
existing `config.toml` and writes the incoming default to `config.toml.dist`
beside it, so anything named in the base file lands on a first install and can
never be reconciled afterwards. Set `faramir_overwrite_config=true` to have init
write the base fresh, discarding host edits, which is rarely what you want now
that the settings this project cares about are not in it:

```bash
make faramir ARGS="--extra-vars faramir_overwrite_config=true"
```

Assigned rather than passed after `--`, because make reads a word containing `=`
as a variable assignment and would forward a bare `--extra-vars`.

Neither daemon re-reads its config while running, so the role runs `faramir
reload` when the drop-in changes. That is one command rather than two restarts
because the order matters and is not obvious: the keeper leads, since it decrypts
the file list the broker is then served, and restarting the broker first would
just fetch the old value set.

## The age key is sealed to the TPM

`0400 faramir-keeper` protects the key while the machine runs. Powered off it is
an ordinary file that decrypts every managed secret retroactively, and nothing
in faramir encrypts a disk.

So `init` seals it to this host's TPM and renders the keeper's unit with
`LoadCredentialEncrypted=` in place of `LoadCredential=`, never both: two entries
claiming one credential name is a unit systemd refuses to start. The keeper is
unchanged by this: the credential keeps the name `age_key`, so it reads the same
path under `$CREDENTIALS_DIRECTORY` and never learns which source filled it. The
plaintext then exists only in the unit's credential directory, on tmpfs, readable
by that unit alone.

`init` asserts the host has a TPM rather than skipping quietly, because a host
that silently does not seal its key is the install that looks healthy and
protects less than it appears to. Set `faramir_seal_age_key=false` on a host
without one, and use full-disk encryption instead, which covers the audit log
and swap as well.

**Sealing alone changes nothing.** `/etc/faramir/age.key` stays on disk until
`faramir_remove_plaintext_age_key=true`, which is separate and false by default
because it is the step that cannot be undone. Sealing binds to PCR 7, which
tracks Secure Boot policy: change that state, or clear the TPM, and the blob
stops decrypting. The only way back is sealing the original key again, so do not
set that flag without the key material somewhere you can re-seal from.

Everything short of removing the plaintext is reversible by setting
`faramir_seal_age_key=false` and re-running: the keeper's unit is rendered fresh
each time, so it goes back to reading the file. There is no drop-in to remember
to delete.

## Authorizing the broker on the fleet

The broker's public key has to be in `authorized_keys` for the account ansible
connects as on every managed host:

```bash
make faramir_fleet ASK_PASS=1
```

`faramir_fleet.yml` reads the public key off the controller, installs it on every
host except the controller without `exclusive` so existing keys keep working,
grants that account NOPASSWD sudo, and then pings every host *through the
broker*. That last step separates "installed" from "works": the role can only
report that the broker holds a key, not that anything accepts it.

It is a separate play because it writes to the managed hosts rather than the
controller, and because it is only useful once the controller has a broker with a
key to distribute. Set `faramir_fleet_authorize_key=false` to remove the key
again.

## Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `faramir_user` | `primary_user` | Owns the checkout and runs the build. Never the agent. |
| `faramir_src_dir` | `{{ faramir_user_home }}/src/github.com/andornaut/faramir` | The checkout to build from. |
| `faramir_go_bin_dir` | `/usr/local/go/bin` | Where the `dev` role installs Go. |
| `faramir_dev_group` | `dev` | Shared access to the working tree. |
| `faramir_broker_user` | `faramir-broker` | Policy, redaction, audit log, SSH keys. |
| `faramir_keeper_user` | `faramir-keeper` | Holds the age key; execs nothing but sops. |
| `faramir_exec_user` | `faramir-exec` | Forks brokered commands; holds nothing. |
| `faramir_worktree` | `{{ faramir_user_home }}/src/github.com/andornaut/ansible-ctrl` | Where brokered commands run: the operator's own checkout. Passed as `--share-tree`. |
| `faramir_config_dir` | `{{ faramir_user_home }}/.faramir` | Where `config.toml` and `config.d/` are installed. |
| `faramir_secrets_dir` | `{{ faramir_config_dir }}/secrets` | Where the store lives. Created `2770 root:dev`, and bound into the keeper's namespace by its own unit. |
| `faramir_secrets_files` | `[{{ faramir_secrets_dir }}/ansible-ctrl.sops.yml]` | The managed sops files, written to the config drop-in every run. |
| `faramir_overwrite_config` | `false` | Have init rewrite the base config instead of keeping it. Destructive. |
| `faramir_broker_ssh_key` | `/var/lib/faramir-broker/.ssh/id_ed25519` | The key the broker lends, generated when missing. Empty leaves `[ssh] keys` unset. |
| `faramir_operator_age_key` | `{{ faramir_user_home }}/.config/sops/age/keys.txt` | The operator's own age identity, minted when missing and added to `.sops.yaml` as a second recipient. Empty leaves the keeper as the only one. |
| `faramir_install_agent_config` | `true` | Install faramir's `Read` deny rules into the operator's Claude settings. |
| `faramir_fleet_authorize_key` | `true` | Whether `faramir_fleet.yml` adds or removes the broker's key. |
| `faramir_seal_age_key` | `true` | Seal the age key to the host TPM and have the keeper load it as an encrypted credential. Fails when the host has no TPM. |
| `faramir_remove_plaintext_age_key` | `false` | Delete `/etc/faramir/age.key` once the keeper runs from the sealed credential. Irreversible without the key material. |

Changing a service account name or `faramir_dev_group` here is enough on its own.
`init` renders the config the sockets check and the units that reach the working
tree from the same values, so `allowed_groups` and `SupplementaryGroups=` cannot
disagree. They used to be literals in faramir's own files, which the role had to
grep for, because a mismatch installs cleanly and then refuses every agent
connection.

## After the first run

Group membership is read at login, so log out and back in before `dev` takes
effect.

The faramir checkout ships a verification matrix that runs against the live
install:

```bash
sudo tests/verify.sh
```
