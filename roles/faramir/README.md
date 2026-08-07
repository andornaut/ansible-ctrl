# faramir

Installs the [faramir](https://github.com/andornaut/faramir) secret broker on the
Ansible controller, so a coding agent can run playbooks against the fleet without
being able to read the credentials they use.

Run it with `make faramir`.

## Why its own playbook

The role installs the systemd units, the `/etc/faramir/config.toml` and the
filesystem permissions that confine the agent, and it restarts the broker. A
brokered run that reached these tasks would rewrite its own confinement as root
and kill the command doing the rewriting, so the role is applied by `faramir.yml`
to a `faramir` inventory group and is reachable from no other play. It is not a
tag in `dev` for that reason: `make dev` is exactly the run an agent is most
likely to trigger.

There is no circular dependency with the rest of this repo. Installing faramir is
an operator action run directly against the controller; brokering playbooks is an
agent action run later. Ansible never needs faramir in order to run.

## Prerequisite: the secrets have to be in sops

The keeper decrypts sops and nothing else. Any credential still held in
`group_vars/all/vault.yml` is absent from the keeper's value set, which means it
is neither injectable through `--env` nor present in the redactor, so a playbook
that prints it prints it in plaintext.

A broker installed before the migration comes up healthy and protects nothing,
which is indistinguishable from a working install unless something says so. The
role prints what the broker loaded and then fails when it loaded nothing. A
staged migration that means to pass through that state sets
`faramir_require_secrets=false`.

### The migration, in order

The controller has to have a broker before the secrets can move, because the
age key that encrypts them is minted by phase 2. So faramir is installed first,
against the unmigrated vault, and the secrets follow:

```bash
make faramir -- --extra-vars faramir_require_secrets=false
```

Then, as the operator, in the *operator's* checkout:

```bash
# 1. Re-encrypt. Names are preserved exactly, so nothing that reads them changes.
install/migrate-vault.sh group_vars/all/vault.yml group_vars/all/vault.sops.yml

# 2. Map each name to the environment. group_vars/ is gitignored, so this is
#    written by hand and copied into the agent's tree with the rest of it.
#    vars.yml sorts before vault.yml, so ansible keeps using the vault until
#    step 3 removes it: adding this changes nothing on its own.
for k in $(sops -d group_vars/all/vault.sops.yml | grep -oE '^[a-z_]+'); do
    echo "${k}: \"{{ lookup('env', '${k}') }}\""
done > group_vars/all/vars.yml

# 3. Prove it works before deleting anything.
sops exec-env group_vars/all/vault.sops.yml 'make homeautomation -- --check'
git rm group_vars/all/vault.yml
```

`host_vars/` needs no change at all: it refers to `{{ vault_* }}`, and those
names now resolve through `group_vars/all/vars.yml` instead of the vault.

Afterwards `make faramir` runs without the override, and its own check confirms
the broker loaded all eleven.

> [!WARNING]
> The vault blob stays in git history, and the vault password still opens it.
> Rotate every credential that was ever committed, or rewrite history. Moving to
> sops does not un-leak what is already there.

### Running playbooks afterwards

`make` is yours. It wraps itself in `sops exec-env` when the values are not
already in the environment, so there is one command and nothing to remember:

```bash
make homeautomation                      # reaches controller, so it asks for sudo
make homeautomation -- --limit siteb   # does not, so it does not ask
make faramir_fleet ASK_PASS=1            # forces the prompt (see below)
```

Whether it prompts is decided per run, from two things ansible is asked in a
single call that connects to nothing:

- **which hosts the run targets**, honouring any `--limit` you passed
- **which roles it pulls in**, because a role can reach the controller without
  targeting it. `make torrent` targets torrentbox, and still writes
  `/usr/local/bin/mvt` and a cron file on controller through
  `delegate_to: localhost`, which no host list ever shows.

It prompts if either the controller is targeted or one of those roles delegates
to it. controller's sudo asks for a password; the fleet is NOPASSWD, so a fleet-only
run needs nothing.

The delegation check greps the roles the run actually named, so a role that
gains a `delegate_to: localhost` is covered without anyone updating a list. It
errs toward asking: a delegation naming a remote host would prompt for nothing,
which costs a keystroke, where not asking costs a half-applied run. `ASK_PASS=1`
forces it, which the fleet play needs because it is the run that establishes the
NOPASSWD in the first place.

The agent does not use `make`. It calls ansible directly through the broker,
which keeps the Makefile a purely operator-facing thing:

```bash
faramir run --env-file faramir.env -- \
    ansible-playbook homeautomation.yml --limit '!faramir'
```

`--limit '!faramir'` excludes the controller, which a brokered run cannot
configure anyway. `faramir.env` lives at the repo root and holds refs, never
values. Both paths set the same variable names, which is why one list serves
both.

### No become password in the store

The store holds no sudo password, and must not. `ansible_become_password` for
your account *is* your login password: an agent that extracted it (which the
threat model accepts is possible, `| rev` and `| cut` defeat redaction) could
`su` to you, and on the controller that reaches `/etc/faramir/age.key`. One
leaked value would become every value, retroactively. The rule is that no
credential goes in the store whose compromise would defeat the store.

If your password is the same on controller and the fleet, there is no fleet-only
become password to store either. So brokered runs carry none, and the fleet gets
NOPASSWD sudo instead, which `faramir_fleet.yml` installs alongside the key.

> [!IMPORTANT]
> A brokered run reaches the *fleet*, not the controller. Commands run as
> `faramir-exec`, which has no sudo, so a brokered playbook can configure
> laptop, gamesbox, siteb and torrentbox over SSH, and cannot apply a `become`
> task to controller itself. Granting that uid sudo on the controller would hand the
> agent root on the machine holding the age key, which is the one thing the
> whole arrangement exists to prevent. Apply controller's own playbooks as the
> operator.

## What the role does

`faramir` publishes no release binaries, so the role builds them from the
checkout at `faramir_src_dir` with `make build` (Go, from the `dev` role), then
runs the project's own four install phases as root:

| Phase | Script | Establishes |
| --- | --- | --- |
| 1 | `install/10-accounts.sh` | the `agent`, `faramir-keeper`, `faramir-broker` and `faramir-exec` uids, the `devwork` group, working tree permissions |
| 2 | `install/20-sops-init.sh` | the age keypair at `/etc/faramir/age.key` (0400, keeper-owned) and `.sops.yaml` in the working tree |
| 3 | `install/30-install-broker.sh` | binaries, `/etc/faramir/config.toml`, systemd units |
| 4 | `install/40-agent-config.sh` | the agent account's Claude settings, the working tree's `.mcp.json` and `CLAUDE.md` snippet |

Calling the scripts rather than reimplementing them keeps one installer: the unit
set, the uid layout and the config schema are faramir's to change, and a
reimplementation here would silently drift from them.

Before phase 1, the role reads `faramir_config_src` with the broker binary it
just built and refuses a config that does not parse, or whose `[exec]
default_cwd` is not `@WORKTREE@` and not inside `faramir_worktree`. Phase 3
applies the same rule, but only after the binaries and the hook are on the host,
where a rejection leaves the install half-applied. Checking it here means a
mismatch stops the run before anything touches root.

Phase 1 runs before the working tree is required, because phase 1 is what
creates the `agent` account and the tree lives in that account's home. Phase 1
is written to tolerate a missing tree: it reports `SKIP` and leaves the group
and setgid bits for a later run.

The cost is that the scripts report no machine-readable change, so each task's
`changed_when` is derived from the state that phase establishes, checked before
any phase runs. Two things this under-reports: phase 1 re-applies the working
tree's group and setgid bits every run, and phase 3 rewrites the unit files and
bind-mount drop-ins every run. Neither shows up as changed.

## The working tree

`faramir_worktree` is the agent's own checkout of this repo, not the operator's.
Brokered commands run there and the sops files are read from there. It has to be
the agent's own because the operator's home is 0700: uid `agent` cannot read the
operator's checkout at all, so sharing one tree is not an option to weigh.

The path lives in `/etc/faramir/config.toml` and nowhere else. The systemd units
name no tree and the installer writes no drop-ins; what keeps a brokered command
out of everything else is the file mode, and `ProtectSystem=strict` makes the
whole hierarchy read-only apart from `/home`.

The role requires it to exist and does not create it: `hosts`, `host_vars/` and
`group_vars/` are gitignored, so a fresh clone would produce a tree that parses
but has no inventory.

A first install is therefore two passes. The first creates the accounts and
stops, naming the account it just made:

```bash
make faramir            # creates the accounts, then stops: no working tree yet

# https, not git@github.com: the agent account holds no SSH key of its own.
sudo -u agent git clone https://github.com/andornaut/ansible-ctrl.git \
    /home/agent/work/ansible-ctrl

# As root, because the operator's home is 0700 and that account cannot read it.
sudo cp -a ~/src/github.com/andornaut/ansible-ctrl/{hosts,host_vars,group_vars} \
    /home/agent/work/ansible-ctrl/
sudo chown -R agent:devwork /home/agent/work/ansible-ctrl

make faramir
```

The second pass applies the tree's group and setgid bits and installs the rest.

## The broker's SSH identity

Brokered commands run as `faramir-exec`, which must be able to *use* the key
that reaches the fleet without being able to read it. The broker holds the key
under its own uid, loads it into an `ssh-agent` it owns, and passes the child
only `SSH_AUTH_SOCK`.

The shipped `ansible-fleet.toml` names `/var/lib/faramir-broker/.ssh/id_ed25519`
and nothing in faramir creates it. A broker started without it logs one warning
and carries on: every socket comes up active, `--check` passes, and every
brokered playbook then fails to reach a single managed host. That is the same
"healthy and protecting nothing" shape as an unmigrated vault, so the role
treats it the same way.

The role generates the key if it is missing, and afterwards asks the running
broker what its agent actually holds:

```
faramir run -- ssh-add -l
```

asked through the broker rather than read off disk, because what matters is
what a brokered command gets. It fails the run when the agent holds nothing.

**Generating the key grants nothing.** Its public half has to be added to
`~/.ssh/authorized_keys` for the account ansible connects as on every managed
host, which this role does not do. The public key is printed at the end of
every run for that reason.

Set `faramir_manage_broker_ssh_key=false` when the config leaves `[ssh] keys`
empty. That is a working setup and not a recommended one: the keys then have to
live where the executor's own uid can read them, which is what holding them in
the broker exists to avoid.

## config.toml is install-once

Phase 3 keeps an existing `/etc/faramir/config.toml` and writes the incoming
default to `config.toml.dist` beside it, already `@WORKTREE@`-substituted so it
can be moved into place as-is. Re-running this role therefore does not reconcile
the installed config. That is deliberate on faramir's side: the installed config
is where `[ssh] keys` and `[secrets] files` get edited.

To have the role rewrite it from `faramir_config_src`:

```bash
make faramir -- --extra-vars faramir_overwrite_config=true
```

This deletes the installed config first, so edits made on the host are lost.

## Authorizing the broker on the fleet

Generating the broker's key grants nothing. Its public half has to be in
`authorized_keys` for the account ansible connects as on every managed host:

```bash
make faramir_fleet
```

`faramir_fleet.yml` reads the public key off the controller and installs it on
every host except the controller itself, without `exclusive`, so the operator's
own key keeps working. It is a separate play because it writes to production
hosts rather than to controller, and because it is only useful once controller has a broker
with a key to distribute.

Set `faramir_fleet_authorize_key=false` to remove it again.

## Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `faramir_user` | `primary_user` | Owns the checkout and runs the build. Never the agent. |
| `faramir_src_dir` | `{{ faramir_user_home }}/src/github.com/andornaut/faramir` | The checkout to build from. |
| `faramir_go_bin_dir` | `/usr/local/go/bin` | Where the `dev` role installs Go. |
| `faramir_agent_user` | `agent` | The uid the coding agent runs as. |
| `faramir_devwork_group` | `devwork` | Shared access to the working tree. |
| `faramir_broker_user` | `faramir-broker` | Policy, redaction, audit log, SSH keys. |
| `faramir_keeper_user` | `faramir-keeper` | Holds the age key; execs nothing but sops. |
| `faramir_exec_user` | `faramir-exec` | Forks brokered commands; holds nothing. |
| `faramir_worktree` | `{{ faramir_agent_user_home }}/work/ansible-ctrl` | Where brokered commands run. |
| `faramir_config_src` | `etc/examples/ansible-fleet.toml` | Config to install, relative to `faramir_src_dir`. |
| `faramir_overwrite_config` | `false` | Discard the installed config and rewrite it. Destructive. |
| `faramir_require_secrets` | `true` | Fail when the broker loads no secret refs. |
| `faramir_broker_ssh_key` | `/var/lib/faramir-broker/.ssh/id_ed25519` | The key the broker lends. Must match `[ssh] keys` in the config. |
| `faramir_manage_broker_ssh_key` | `true` | Generate that key, and fail when the broker's agent holds none. |
| `faramir_operator_age_key` | `{{ faramir_user_home }}/.config/sops/age/keys.txt` | The operator's own age identity, added to `.sops.yaml` as a second recipient. |
| `faramir_manage_operator_age_key` | `true` | Mint that identity and list it. False leaves the keeper as the only recipient. |
| `faramir_fleet_authorize_key` | `true` | Whether `faramir_fleet.yml` adds or removes the broker's key. |

Changing a service account name here is not enough on its own: the shipped
systemd units and `config.toml` name them too.

## After the first run

Group membership is read at login, so the operator and the agent both have to log
out and back in before `devwork` takes effect.

The faramir checkout ships a verification matrix that runs against the live
install:

```bash
sudo tests/verify.sh
```
