# faramir

Installs the [faramir](https://github.com/andornaut/faramir) secret broker on the Ansible controller, so a coding agent can run playbooks against the fleet without being able to read the credentials they use.

faramir's own [README](https://github.com/andornaut/faramir#readme) covers what it protects against, the accounts and units, the config model, and the store. None of that is restated here: this role's docs cover what belongs to this repo, which is how to install the broker here and how to run these playbooks through it.

## Usage

```bash
make faramir                     # install and reconcile the broker on the controller
make faramir_fleet ASK_PASS=1    # authorize the broker's key on the managed hosts
```

Both are operator actions. `faramir.yml` applies this role to the `faramir` inventory group and no other play reaches it: a brokered run would rewrite its own confinement as root and kill the command doing the rewriting.

Log out and back in after the first install. It adds you to `faramir_dev_group`, and group membership is read at login.

The role has two entry points. `tasks/main.yml` installs the broker on the controller, and is what `faramir.yml` applies. `tasks/ssh.yml` authorizes that broker's key across the fleet, and is what `faramir_fleet.yml` applies, over `hosts: all` and with `tasks_from: ssh` so nothing else in the role runs there: it reads the key off the controller, installs it on every other host without `exclusive`, grants that account NOPASSWD sudo, then pings every host back through the broker. Separate because the second writes to production hosts and is useful only once the first has produced a key to distribute.

The controller is named: `faramir_controller` is `controller`, matched against `inventory_hostname`. `main.yml` refuses to run on any other host, before it reads anything, because the install creates service accounts, systemd units and the age key, and a `hosts:` pattern meant for the controller that reached the fleet instead would provision the fleet. The working-tree check further down is not that backstop: a host with a directory at the same path passes it.

`ssh.yml` requires the `faramir` group to hold that host and no other. Two controllers is an error rather than a configuration: the fleet authorizes one broker's key, so a second member would mean distributing one of the two brokers' keys and refusing the other's brokered runs everywhere, silently. Taking the group's first member would have made that mistake quietly survivable; comparing against the name makes it a failure that says which host the group holds and which one it should.

Asserted rather than `delegate_to: localhost`, which is how the `torrent` role reaches the controller from a play targeting somewhere else. Delegation would not stop this and would hide it: a delegated task resolves plain variables from the play host rather than the delegate, so a role applied to the fleet would install here once per host, each run using that host's `primary_user` and config path.

One play, where that was three. The default linear strategy runs each task on every host before starting the next, so the key is published before the first host is asked to authorize it, and every host has been asked before the brokered ping goes looking for it.

## Running playbooks

`homeautomation`, `msmtp` and `webservers` read a credential and re-enter under `sops exec-env`. The other twelve targets run straight through.

| Run | Command |
| --- | --- |
| no credential | `make <playbook>` |
| credential, controller | `sudo make <playbook> -- --limit <controller>` |
| credential, fleet | `faramir run --env-file faramir.env -- ansible-playbook <playbook>.yml --limit '!faramir'` |

Neither account covers the whole fleet: root has no key for a host it must reach over ssh, and the executor has no sudo on the controller. `make` refuses a run it cannot serve and prints both commands.

`faramir.env` holds refs, never values. Both paths set the same variable names, so one list serves both.

`--ask-become-pass` is added only when the run reaches the controller, decided per run by one ansible call that connects to nothing. Roles are checked as well as hosts, because `delegate_to: localhost` reaches the controller without appearing in any host list. It errs toward asking, and a run already root is never asked. `ASK_PASS=1` forces it, which `faramir_fleet.yml` needs: that is the run establishing the NOPASSWD which makes prompting unnecessary.

## Constraints

- **Every credential lives in the store**, `~/.faramir/secrets/ansible-ctrl.sops.yml`. A credential held anywhere else is absent from the broker's value set: neither injectable through `--env` nor known to the redactor, so a playbook that prints it prints plaintext.
- **The store must never sit under `group_vars/` or `host_vars/`.** Ansible auto-loads every `.yml` there and a sops file is valid YAML, so each var binds to its `ENC[...]` ciphertext. Nothing errors; hosts get the ciphertext as the password. `faramir init` refuses to finish against a store under either directory.
- **The store must not be in the checkout.** This is a public repo, and a store inside it is ciphertext of every credential one `git add -f` from publication.
- **No sudo password in the store.** `ansible_become_password` for the operator is their login password, and the agent already runs as that account: with the password it has sudo, on the controller that is root, and root reads the keeper's age key. The fleet gets NOPASSWD sudo instead, installed by `tasks/ssh.yml`.
- **A brokered run reaches the fleet, not the controller**, hence `--limit '!faramir'`. Commands run as `faramir-exec`, which has no sudo here, and granting it any would hand the agent root on the machine holding the age key. Apply the controller's own playbooks as the operator.
- **Nothing under the home is readable before first login.** Config and store both sit in the operator's encrypted home, so a reboot leaves the store absent and a 03:00 renewal on an unmounted home does not run. Point `faramir_config_dir` at an unencrypted filesystem and that trade changes.

## What the role does

`faramir init`, run once as root with this project's paths, establishes the accounts, the age key, `.sops.yaml`, the broker's SSH identity, the directories, the config, the units and their sandboxing. What belongs to this project rather than to faramir:

| Step | Why it is here |
| --- | --- |
| downloading the binary | faramir publishes releases but installs no package |
| `faramir init-project` against `playbook_dir` | which tree the agent works in is this repo's to say |
| the `AGENTS.md` block | how to run *these* playbooks through the broker |
| `faramir doctor` and its assert | the run has to fail when the result does not work, and a playbook is what fails |

`init` reports per step in JSON, so `changed_when` reads a field; under `--check` the role passes `--dry-run`, which computes every answer and writes nothing.

The binary comes from faramir's rolling `dev` release: one ~7MB archive a run into a temp directory, unpacked, `init` run from it (which installs the binary it was run from), directory removed. No Go toolchain and no faramir checkout on the controller. `get_url` verifies against `checksums.txt` from the same release, so a download straddling a re-cut of `dev` fails the checksum rather than installing a build that was never verified. `faramir_arch` maps the kernel name onto the asset's; the kernel is not mapped, faramir being linux-only.

Enrol another tree with `cd <dir> && sudo faramir init-project`. Anything this role writes into the enrolled tree is written group-writable to match what `init-project` leaves behind, `AGENTS.md` included: a mode withheld from one file there is re-granted by the next enrolment and withheld again by the next run, which is a task that reports a change forever and protects nothing.

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

A broker that loaded no refs comes up healthy and protects nothing, so the role asserts on `faramir doctor`'s report rather than on the units being up. Run `sudo faramir doctor` by hand to get the boundary checks as well, which ask each account what it can reach and need a uid other than your own.

## Variables

See [defaults/main.yml](./defaults/main.yml). Service account names and `faramir_dev_group` are free to change here: `init` renders both the config and the units from the same values.
