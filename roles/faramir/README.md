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

## Where the credentials have to be

The keeper decrypts sops and nothing else, so every credential this repo uses
lives in `secrets/vault.sops.yml`, `group_vars/all/vars.yml` maps each name to
`lookup('env', ...)`, and `host_vars/` refers to the names. A credential held
anywhere else is absent from the keeper's value set, which means it is neither
injectable through `--env` nor present in the redactor: a playbook that prints
it prints it in plaintext.

The encrypted file belongs in `secrets/`, never under `group_vars/`. Ansible
auto-loads every `.yml` under `group_vars/` and `host_vars/`, and a sops file is
valid YAML, so it would bind each var to its `ENC[...]` ciphertext. Nothing
errors; hosts just get the ciphertext as the password. The role asserts on this
after install.

A broker whose secrets file it cannot read comes up healthy and protects
nothing, which is indistinguishable from a working install unless something says
so. The role prints what the broker loaded and fails when a managed sops file
exists and yielded no refs.

To prove the brokered path resolves a var end to end:

```bash
faramir run --env-file faramir.env -- \
    ansible tron -m debug -a 'var=secret_msmtp_password'
# -> "secret_msmtp_password": "«SECRET:secret_msmtp_password»"
```

That one command covers the whole chain: the ref decrypted, the value reached
the child's environment, `lookup('env', ...)` found it, and the redactor
replaced it on the way back. Any other output is a fault. A bare name means the
ref was not injected; `ENC[AES256_GCM,...]` means the encrypted file is
somewhere Ansible auto-loads it.

### Running playbooks

`make` is yours. It wraps itself in `sops exec-env` when the values are not
already in the environment, so there is one command and nothing to remember:

```bash
make homeautomation                      # reaches tron, so it asks for sudo
make homeautomation -- --limit snorlax   # does not, so it does not ask
make faramir_fleet ASK_PASS=1            # forces the prompt (see below)
```

Whether it prompts is decided per run, from two things ansible is asked in a
single call that connects to nothing:

- **which hosts the run targets**, honouring any `--limit` you passed
- **which roles it pulls in**, because a role can reach the controller without
  targeting it. `make torrent` targets prime, and still writes
  `/usr/local/bin/mvt` and a cron file on tron through
  `delegate_to: localhost`, which no host list ever shows.

It prompts if either the controller is targeted or one of those roles delegates
to it. tron's sudo asks for a password; the fleet is NOPASSWD, so a fleet-only
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

If your password is the same on tron and the fleet, there is no fleet-only
become password to store either. So brokered runs carry none, and the fleet gets
NOPASSWD sudo instead, which `faramir_fleet.yml` installs alongside the key.

> [!IMPORTANT]
> A brokered run reaches the *fleet*, not the controller. Commands run as
> `faramir-exec`, which has no sudo, so a brokered playbook can configure
> thinkpad, nomnomnom, snorlax and prime over SSH, and cannot apply a `become`
> task to tron itself. Granting that uid sudo on the controller would hand the
> agent root on the machine holding the age key, which is the one thing the
> whole arrangement exists to prevent. Apply tron's own playbooks as the
> operator.

## What the role does

`faramir` publishes no release binaries, so the role builds them from the
checkout at `faramir_src_dir` with `make build` (Go, from the `dev` role), then
runs the project's own four install phases as root:

| Phase | Script | Establishes |
| --- | --- | --- |
| 1 | `install/10-accounts.sh` | the `faramir-keeper`, `faramir-broker` and `faramir-exec` uids, the `dev` group, working tree permissions |
| 2 | `install/20-sops-init.sh` | the age keypair at `/etc/faramir/age.key` (0400, keeper-owned) and `.sops.yaml` in the working tree |
| 3 | `install/30-install-broker.sh` | binaries, `/etc/faramir/config.toml`, systemd units |
| 4 | `install/40-agent-config.sh` | your Claude settings, the working tree's `.mcp.json` and `CLAUDE.md` snippet |

Calling the scripts rather than reimplementing them keeps one installer: the unit
set, the uid layout and the config schema are faramir's to change, and a
reimplementation here would silently drift from them.

Before phase 1, the role reads `faramir_config_src` with the broker binary it
just built and refuses a config that does not parse. Phase 3 applies the same
rule, but only after the binaries and the hook are on the host, where a
rejection leaves the install half-applied. Checking it here means a bad config
stops the run before anything touches root.

Phase 1 is written to tolerate a missing tree: it reports `SKIP` and leaves the
group and setgid bits for a later run.

The cost is that the scripts report no machine-readable change, so each task's
`changed_when` is derived from the state that phase establishes, checked before
any phase runs. Two things this under-reports: phase 1 re-applies the working
tree's group and setgid bits every run, and phase 3 rewrites the unit files
every run. Neither shows up as changed.

## The working tree

`faramir_worktree` is your own checkout of this repo.
Brokered commands run there and the sops files are read from there. It has to be reachable by
`faramir-keeper`, which decrypts the sops files in it, and `faramir-exec`, which
runs brokered commands in it. Neither is your uid and a home is 0700, so phase 1
grants those two traversal with an ACL on every component from your home down.
Not `chmod o+x`, which would give every account on the machine the same thing.

On an ecryptfs home that ACL is write-once. The first `setfacl` against an inode
applies; every later one is silently ignored, exiting 0 while changing nothing,
so an entry left out of the first call cannot be added afterwards. Grant every
uid in a single call and read the result back with `getfacl` rather than
trusting the exit status. The entries can still be corrected on the lower
directory (`/home/.ecryptfs/<user>/.Private`), which is ext4, but the mount does
not see the change until it is remounted.

Point it outside the homes instead (`/srv/faramir/ansible-ctrl`) and no ACL is
needed. The cost is that it stops being the checkout you work in, which is what
having one copy was for.

The path lives in `/etc/faramir/config.toml` and nowhere else. The systemd units
name no tree and the installer writes no drop-ins; what keeps a brokered command
out of everything else is the file mode, and `ProtectSystem=strict` makes the
whole hierarchy read-only apart from `/home`.

The role requires it to exist and does not create it: `hosts`, `host_vars/`,
`group_vars/` and `secrets/` are gitignored, so a fresh clone would produce a
tree that parses but has no inventory and no secrets.

The tree is the checkout you already work in, so `make faramir` is a single pass
and there is one copy of the inventory rather than two to keep in step.

## The broker's SSH identity

Brokered commands run as `faramir-exec`, which must be able to *use* the key
that reaches the fleet without being able to read it. The broker holds the key
under its own uid, loads it into an `ssh-agent` it owns, and passes the child
only `SSH_AUTH_SOCK`.

The shipped `ansible-fleet.toml` names `/var/lib/faramir-broker/.ssh/id_ed25519`
and nothing in faramir creates it. A broker started without it logs one warning
and carries on: every socket comes up active, `--check` passes, and every
brokered playbook then fails to reach a single managed host. That is the same
"healthy and protecting nothing" shape as a secrets file the keeper cannot read,
so the role treats it the same way.

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
make faramir_fleet ASK_PASS=1
```

Run it once the broker has a key to distribute. Its last step pings every host
through the broker, so it needs a working brokered ansible.

`faramir_fleet.yml` reads the public key off the controller, installs it on
every host except the controller itself without `exclusive` so your own key
keeps working, grants that account NOPASSWD sudo, and then proves the chain by
pinging every host *through the broker*. That last step is the difference
between "installed" and "works": the role can only tell you the broker holds a
key, not that anything accepts it.

It is a separate play because it writes to production hosts rather than to tron,
and because it is only useful once tron has a broker with a key to distribute.

Set `faramir_fleet_authorize_key=false` to remove it again.

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
| `faramir_worktree` | `{{ faramir_user_home }}/src/github.com/andornaut/ansible-ctrl` | Where brokered commands run: your own checkout. |
| `faramir_config_src` | `etc/examples/ansible-fleet.toml` | Config to install, relative to `faramir_src_dir`. |
| `faramir_overwrite_config` | `false` | Discard the installed config and rewrite it. Destructive. |
| `faramir_broker_ssh_key` | `/var/lib/faramir-broker/.ssh/id_ed25519` | The key the broker lends. Must match `[ssh] keys` in the config. |
| `faramir_manage_broker_ssh_key` | `true` | Generate that key, and fail when the broker's agent holds none. |
| `faramir_operator_age_key` | `{{ faramir_user_home }}/.config/sops/age/keys.txt` | The operator's own age identity, added to `.sops.yaml` as a second recipient. |
| `faramir_manage_operator_age_key` | `true` | Mint that identity and list it. False leaves the keeper as the only recipient. |
| `faramir_fleet_authorize_key` | `true` | Whether `faramir_fleet.yml` adds or removes the broker's key. |

Changing a service account name here is not enough on its own: the shipped
systemd units and `config.toml` name them too.

## After the first run

Group membership is read at login, so log out and back in before `dev` takes
effect.

The faramir checkout ships a verification matrix that runs against the live
install:

```bash
sudo tests/verify.sh
```
