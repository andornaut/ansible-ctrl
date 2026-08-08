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

The store lives in the operator's home, inside `faramir_config_dir` along with
the config and the age key. The agent runs as that account and its own age
identity is in that home, so it can already decrypt the ciphertext wherever it
sits: moving the file costs nothing, and it is what puts the store and the key
that opens it on the same encrypted disk.

What confines the agent there is mode and uid rather than location. The age key
is `0400 faramir-keeper`, so owning the directory around it is permission to
unlink the file and not to read it. The units define the three service uids and
the binaries are what enforce any of it, and those stay outside every home.

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

The role downloads faramir's six binaries into a temporary directory and runs
`faramir init` once, as root, with this project's paths on the command line.
That one command establishes the accounts and the `dev` group, the age key,
`.sops.yaml`, the broker's SSH identity, the directories, the binaries, the hook,
the config, the systemd units and their sandboxing, and the sockets. None of it is restated here: a setting named in both places is one that
can disagree with itself.

What is left for the role is the part that belongs to this project rather than to
faramir:

| Step | Why it is here and not in faramir |
| --- | --- |
| `faramir init-project` against `playbook_dir` | which tree the agent works in is this repo's to say; the enrolment itself is faramir's |
| the `config.d/ansible-ctrl.toml` drop-in | which sops files the broker manages is this repo's, and faramir ships no list of them |
| `faramir reload` when that changes | the drop-in is the role's to write, so getting the daemons onto it is the role's to trigger |
| the `AGENTS.md` block | how to run *these* playbooks through the broker, which faramir's own snippet says nothing about |
| `faramir doctor` and its assert | the run has to fail when the result does not work, and a playbook is what fails |
| the `CLEANUP` tasks | faramir installs and never migrates, so repairing what an earlier layout left behind is this role's, in tasks that are deleted once the fleet has converged |

That last row is the rule, not an accident of where things ended up. A repair
built into `faramir init` cannot know when every host has run it, so it would be
carried forever and every install would be a migration. Kept here, each one is a
`CLEANUP (added YYYY-MM-DD)` task that is deleted once it has run everywhere,
after which an install is a first install again.

`init` reports per step in JSON, so `changed_when` reads a field rather than
inferring one from stat-ing the host before and after. Under `--check` the role
passes `--dry-run`, which computes every answer and writes nothing.

## Where the binaries come from

faramir's CI cuts a `dev` release on every push to its `main`, holding the six
binaries as bare assets. The role downloads them into a temp directory, hands
that directory to `init`, and removes it: what is installed is what `init`
copied into `/usr/local/bin`, and a staged copy left on disk would be a second
one that nothing updates. It costs 23MB a run and needs no Go toolchain and no
faramir checkout on the controller.

Nothing but the binaries crosses: the units, the base config, the agent hook and
the docs are embedded in them, so `init` needs no source layout and this role
knows about none. `init` compares each binary against the installed one and
reports what it replaced, so a run that downloads the same build reports no
change.

Two things the `dev` release is not. It is amd64 only, because CI builds it once
on an x86_64 runner and the asset names carry no architecture, which the role
asserts on rather than mapping. And it ships no `checksums.txt`, so the download
is trusted to TLS and to GitHub and to nothing else. Both are fixed by a tagged
release: goreleaser publishes amd64 and arm64 archives with checksums, and
switching to one means changing the fetch as well as the URL. faramir has no `v`
tag yet.

## The working tree

The tree brokered commands run in is the checkout the play was run from,
`playbook_dir`. There is no variable naming it: the operator's own checkout is
the one place the inventory lives, and a variable pointing anywhere else would
enrol a tree nobody works in. It also means this role applies only to the
controller holding that checkout, which is the only host it was ever meant for.

Brokered commands run there, so it has to be reachable by `faramir-exec`, and by
nothing else: the sops files are read from `faramir_secrets_dir`, which the
keeper sees through a bind of that one directory and nothing else of the home
around it.

`faramir-exec` is not the operator's uid and a home is 0700, so the role passes
that checkout to `faramir init-project`, which the role runs after `init`: it
group-owns the tree and sets the setgid bits, so a brokered command and the
operator stop fighting over each other's files, and makes every directory
group-executable from the home down. Not `chmod o+x`, which with `umask 002` in
force would open the whole home rather than a path through it.

`init-project` also registers the `PreToolUse` hook in this checkout's own
`.claude/settings.json`, writes `.mcp.json`, and splices faramir's credentials
block into `AGENTS.md`. Set `faramir_project_hook=false` to share the tree
without the hook, which keeps Bash prompts here and gives up redaction with them.

It is a separate command from `init` rather than a flag on it, because a host is
provisioned once and there is no limit to how many trees you work in. It reads
the shared group out of the config `init` installed rather than being told it a
second time, so a tree cannot end up group-owned by something the broker socket
does not admit. Enrol another the same way: `cd <dir> && sudo faramir
init-project`, which defaults to where you are standing.

The role checks that the tree exists on the target before it installs anything. `playbook_dir` is a controller-side path, and it is the target's too
only because the host this role applies to is the controller; a remote host in
the `faramir` group would be handed a directory that need not exist there, and
that check is what says so before the run has done any work.

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
a brokered command gets. `init` fails when the agent holds nothing, which is what
fails the play, since the role runs `init` every time. `doctor` reports it as a
warning instead: it is not told whether a key was meant to be configured, so it
cannot tell an install that lost its key from one that never wanted one.

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

## The age key, and what it is worth at rest

`0400 faramir-keeper` protects the key while the machine runs, and it is what
keeps the operator out of it wherever the key sits: owning the directory is
permission to unlink the file, not to read it. Replacing it is a deliberate act,
and a store encrypted to the key it replaced then decrypts for nobody, so what
that buys is denial of service rather than disclosure.

The key lives beside the config, which means inside `faramir_config_dir` and so
inside the operator's encrypted home. That is the whole of the at-rest story: the
store is in there too, so a powered-off disk carries neither the ciphertext nor
the key that opens it. `/etc/faramir` is gone once a run has moved the key out of
it.

It holds only while both stay there. Point `faramir_config_dir` at an
unencrypted filesystem and the key and the store are back on the same ordinary
disk, at which point full-disk encryption is the answer, and it covers the audit
log and swap as well.

Nothing starts the keeper at boot: its unit is triggered only by its socket, so
a key in a home is read after login, which is when the home is there.

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
| `faramir_user` | `primary_user` | Owns the working tree and the config. Never the agent. |
| `faramir_dev_group` | `dev` | Shared access to the working tree. |
| `faramir_broker_user` | `faramir-broker` | Policy, redaction, audit log, SSH keys. |
| `faramir_keeper_user` | `faramir-keeper` | Holds the age key; execs nothing but sops. |
| `faramir_exec_user` | `faramir-exec` | Forks brokered commands; holds nothing. |
| `faramir_project_hook` | `true` | Register the `PreToolUse` hook in the checkout. Redacts everything the agent runs here, and auto-approves Bash here as a consequence. |
| `faramir_config_dir` | `{{ faramir_user_home }}/.faramir` | Where `config.toml` and `config.d/` are installed. |
| `faramir_secrets_dir` | `{{ faramir_config_dir }}/secrets` | Where the store lives. Created `2770 root:dev`, and bound into the keeper's namespace by its own unit. |
| `faramir_secrets_files` | `[{{ faramir_secrets_dir }}/ansible-ctrl.sops.yml]` | The managed sops files, written to the config drop-in every run. |
| `faramir_overwrite_config` | `false` | Have init rewrite the base config instead of keeping it. Destructive. |
| `faramir_broker_ssh_key` | `/var/lib/faramir-broker/.ssh/id_ed25519` | The key the broker lends, generated when missing. Empty leaves `[ssh] keys` unset. |
| `faramir_operator_age_key` | `{{ faramir_user_home }}/.config/sops/age/keys.txt` | The operator's own age identity, minted when missing and added to `.sops.yaml` as a second recipient. Empty leaves the keeper as the only one. |
| `faramir_install_agent_config` | `true` | Install faramir's `Read` deny rules into the operator's Claude settings. |
| `faramir_fleet_authorize_key` | `true` | Whether `faramir_fleet.yml` adds or removes the broker's key. |

Changing a service account name or `faramir_dev_group` here is enough on its own.
`init` renders the config the sockets check and the units that reach the working
tree from the same values, so `allowed_groups` and `SupplementaryGroups=` cannot
disagree. They used to be literals in faramir's own files, which the role had to
grep for, because a mismatch installs cleanly and then refuses every agent
connection.

## After the first run

Group membership is read at login, so log out and back in before `dev` takes
effect.

faramir ships a verification matrix that runs against the live install. The role
installs no checkout, so this needs one:

```bash
git clone git@github.com:andornaut/faramir.git && cd faramir && sudo tests/verify.sh
```
