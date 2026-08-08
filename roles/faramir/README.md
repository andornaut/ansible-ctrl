# faramir

Installs the [faramir](https://github.com/andornaut/faramir) secret broker on the
Ansible controller, so a coding agent can run playbooks against the fleet without
being able to read the credentials they use.

Run it with `make faramir`.

## Why its own playbook

The role writes the systemd units, `/etc/faramir/config.toml` and the filesystem
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
Every credential therefore lives in `/etc/faramir/secrets/ansible-ctrl.sops.yml`,
`group_vars/all/vars.yml` maps each name to `lookup('env', ...)`, and
`host_vars/` refers to the names.

The encrypted file lives under `/etc` rather than in this checkout, because an
encrypted home is not mounted at boot or under cron: a secrets file inside one
leaves the broker holding an empty value set until the operator's first login,
and leaves the certificate renewal job unable to read anything at all. The
directory is `2770 root:dev`, so `sops` still edits it in place without sudo.

It must also never sit under `group_vars/` or `host_vars/`. Ansible auto-loads
every `.yml` there and a sops file is valid YAML, so each var would bind to its
`ENC[...]` ciphertext. Nothing errors; hosts get the ciphertext as the password.
The role asserts against this after install.

A broker whose secrets file it cannot read comes up healthy and protects nothing.
The role prints what the broker loaded and fails when a managed sops file exists
and yielded no refs.

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
runs the project's own install phases as root:

| Phase | Establishes |
| --- | --- |
| accounts | the `faramir-keeper`, `faramir-broker` and `faramir-exec` uids, the `dev` group, working tree permissions |
| sops-init | the age keypair at `/etc/faramir/age.key` (0400, keeper-owned) and `.sops.yaml` in `/etc/faramir/secrets` |
| install-broker | binaries, `/etc/faramir/config.toml`, systemd units |
| agent-config | the agent's settings, and the working tree's `.mcp.json` and instructions snippet |

The role validates `faramir_config_src` with the freshly built binary before the
first phase. The installer applies the same rule, but only once the binaries are
on the host, where a rejection leaves the install half-applied.

The scripts report no machine-readable change, so `changed_when` is derived from
the state each phase establishes, sampled before any phase runs. It under-reports
twice: the accounts phase re-applies the working tree's group and setgid bits
every run, and the broker phase rewrites the unit files every run.

## The working tree

`faramir_worktree` is the operator's own checkout of this repo, so there is one
copy of the inventory rather than two to keep in step. Brokered commands run
there, so it has to be reachable by `faramir-exec`, and by nothing else: the
sops files are read from `/etc/faramir/secrets`, so the keeper never opens
anything under a home and its unit sets `ProtectHome=true`. `faramir-exec` is
not the operator's uid and a home is 0700, so the accounts phase grants it
traversal with an ACL on every component from the home down.

The role requires the tree to exist and does not create it: `hosts`, `host_vars/`
and `group_vars/` are gitignored, so a fresh clone parses but has no inventory.

Nothing the broker reads names this tree: neither the systemd units nor the
config. What keeps a brokered command out of everything else is the file mode,
plus `ProtectSystem=strict`, which makes the hierarchy read-only apart from
`/home`.

> [!WARNING]
> On an ecryptfs home the ACL is write-once. The first `setfacl` against an inode
> applies and every later one is silently ignored, exiting 0 while changing
> nothing. Grant every uid in a single call and read the result back with
> `getfacl` rather than trusting the exit status. The entries can still be
> corrected on the lower directory (`/home/.ecryptfs/<user>/.Private`), which is
> ext4, but the mount does not see the change until it is remounted.

## The broker's SSH identity

Brokered commands run as `faramir-exec`, which must be able to use the key that
reaches the fleet without being able to read it. The broker holds the key under
its own uid, loads it into an `ssh-agent` it owns, and passes the child only
`SSH_AUTH_SOCK`.

Nothing in faramir creates that key. A broker started without it logs one warning
and carries on: every socket comes up active, `--check` passes, and every brokered
playbook then fails to reach a single host. The role generates it when missing,
then asks the running broker what its agent holds:

```bash
faramir run -- ssh-add -l
```

Asked through the broker rather than read off disk, because what matters is what
a brokered command gets. The run fails when the agent holds nothing.

Generating the key grants nothing on its own. Its public half has to reach the
managed hosts, which the fleet play below does, and the role prints it at the end
of every run.

Set `faramir_manage_broker_ssh_key=false` when the config leaves `[ssh] keys`
empty. The keys then have to live where the executor's own uid can read them.

## config.toml is install-once

The installer keeps an existing `/etc/faramir/config.toml` and writes the incoming
default to `config.toml.dist` beside it, already substituted so it can be moved
into place as-is. Re-running the role does not reconcile the installed config,
deliberately: that file is where `[ssh] keys` and `[secrets] files` get edited.

To rewrite it from `faramir_config_src`, discarding any edits made on the host:

```bash
make faramir -- --extra-vars faramir_overwrite_config=true
```

## The age key is sealed to the TPM

`0400 faramir-keeper` protects the key while the machine runs. Powered off it is
an ordinary file that decrypts every managed secret retroactively, and nothing
in faramir encrypts a disk.

So the role seals it to this host's TPM and drops in a
`LoadEncryptedCredential=` for the keeper. The keeper is unchanged by this: the
credential keeps the name `age_key`, so it reads the same path under
`$CREDENTIALS_DIRECTORY` and never learns which source filled it. The plaintext
then exists only in the unit's credential directory, on tmpfs, readable by that
unit alone.

The role asserts the host has a TPM rather than skipping quietly, because a host
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

Everything short of removing the plaintext is reversible by deleting
`/etc/systemd/system/faramir-keeper.service.d/tpm-credential.conf`, reloading
systemd and restarting the keeper.

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
| `faramir_worktree` | `{{ faramir_user_home }}/src/github.com/andornaut/ansible-ctrl` | Where brokered commands run: the operator's own checkout. |
| `faramir_config_src` | `etc/examples/ansible-fleet.toml` | Config to install, relative to `faramir_src_dir`. |
| `faramir_overwrite_config` | `false` | Discard the installed config and rewrite it. Destructive. |
| `faramir_broker_ssh_key` | `/var/lib/faramir-broker/.ssh/id_ed25519` | The key the broker lends. Must match `[ssh] keys` in the config. |
| `faramir_manage_broker_ssh_key` | `true` | Generate that key, and fail when the broker's agent holds none. |
| `faramir_operator_age_key` | `{{ faramir_user_home }}/.config/sops/age/keys.txt` | The operator's own age identity, added to `.sops.yaml` as a second recipient. |
| `faramir_manage_operator_age_key` | `true` | Mint that identity and list it. False leaves the keeper as the only recipient. |
| `faramir_fleet_authorize_key` | `true` | Whether `faramir_fleet.yml` adds or removes the broker's key. |
| `faramir_seal_age_key` | `true` | Seal the age key to the host TPM and have the keeper load it as an encrypted credential. Fails when the host has no TPM. |
| `faramir_age_key_cred` | `/etc/faramir/age.key.cred` | Where the sealed credential goes. `0400 root:root`. |
| `faramir_remove_plaintext_age_key` | `false` | Delete `/etc/faramir/age.key` once the keeper runs from the sealed credential. Irreversible without the key material. |

Changing a service account name here is not enough on its own: the shipped
systemd units and `config.toml` name them too. The same holds for
`faramir_dev_group`, which is `allowed_groups` in the config and
`SupplementaryGroups` in the units, and which the role checks against both
because a mismatch installs cleanly and then refuses every agent connection.

## After the first run

Group membership is read at login, so log out and back in before `dev` takes
effect.

The faramir checkout ships a verification matrix that runs against the live
install:

```bash
sudo tests/verify.sh
```
