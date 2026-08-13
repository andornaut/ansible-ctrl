# faramir

Installs the [faramir](https://github.com/andornaut/faramir) secret broker on the Ansible controller, so a coding agent can run playbooks against the fleet without being able to read the credentials they use. What it protects against, its accounts, units, config model and store are in faramir's own [README](https://github.com/andornaut/faramir#readme); this covers what is specific to this repo.

## Usage

```bash
make faramir    # install the broker, then authorize its key on the fleet
```

An operator action. Log out and back in after the first install: it adds you to `faramir_client_group`, and group membership is read at login.

`faramir.yml` applies the role's two entry points in order:

| Play | Entry point | Hosts | Effect |
| --- | --- | --- | --- |
| first | `tasks/broker.yml` (via `tasks/main.yml`) | `faramir` | Installs the broker on the controller |
| second | `tasks/ssh.yml` (`tasks_from`) | `all` | Authorizes the broker's key and NOPASSWD sudo, pins the fleet's host keys in `faramir_fleet_known_hosts_path`, then pings the hosts it still holds back through the broker |

`faramir_controller` names the one host it may install on: `broker.yml` refuses to run anywhere else, and `ssh.yml` requires the `faramir` group to hold that host and no other.

## Running playbooks

`homeautomation`, `msmtp` and `webservers` read a credential and re-enter under `sops exec-env`. The other targets run straight through.

Once the broker is installed the store stops being readable by the operator. `make` routes around that:

| Run | What `make <playbook>` does |
| --- | --- |
| no credential | one `ansible-playbook`, as the operator |
| credential, store readable | one `ansible-playbook`, under `sops exec-env` |
| credential, store unreadable | `sudo make <playbook>`, then the row above |

Root serves such a run whole: it reads the store, and `ANSIBLE_PRIVATE_KEY_FILE` gives it the broker's key, which reaches every managed host. The one password prompt comes before anything applies, so a refused password stops the run with nothing done.

The agent's route is the other one, and takes no password:

```bash
faramir run --env-file faramir.env -- ansible-playbook <playbook>.yml --limit '!faramir'
```

`faramir.env` holds refs and never values.

## Constraints

- **The config directory is `~/.config/faramir`**, holding the age key, the broker's SSH key and the store, so an encrypted home carries all three. `init` grants the client group traversal from the home down, making `~/.config` passable by `faramir-broker` and `faramir-exec`: execute without read. `doctor` fails if `~/.ssh`, `~/.config/sops` or `~/.gnupg` becomes readable by the executor.
- **Every credential lives in the store**, `~/.config/faramir/secrets/ansible-ctrl.sops.yml`. One held anywhere else is neither injectable through `--env` nor known to the redactor, so a playbook that prints it prints plaintext.
- **The store must not sit under `group_vars/` or `host_vars/`**, where Ansible auto-loads every `.yml`: a sops file is valid YAML, so each var binds to its `ENC[...]` ciphertext and hosts get the ciphertext as the password. Nor in the checkout, this repo being public. `faramir init` refuses both.
- **A brokered run reaches the fleet, not the controller**, hence `--limit '!faramir'`: commands run as `faramir-exec`, which has no sudo here. Apply the controller's own playbooks as the operator.
- **The fleet's host keys are pinned system-wide**, in `faramir_fleet_known_hosts_path` (`/etc/ssh/ssh_known_hosts`): ssh verifies a host before authenticating to it, and the executor has no `known_hosts` of its own. Each entry is keyed by the name ssh looks it up under, `faramir_fleet_known_hosts_name`: the bare address on port 22, `[host]:port` otherwise. A key that no longer matches what is pinned fails the play rather than being rewritten.

## What the role adds

`faramir init` establishes the accounts, age key, `.sops.yaml`, SSH identity, directories, config and units. On top of that, the role:

- Downloads the binary from faramir's rolling `dev` release, verified against `checksums.txt` from the same release
- Runs `faramir init-project` against `playbook_dir`, and writes the block covering how to run these playbooks through the broker
- Runs `faramir doctor` and asserts on its report

Enrol another tree with `cd <dir> && sudo faramir init-project`.

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

`sudo faramir doctor` adds the boundary checks, which ask each account what it can reach and need a uid other than your own.

## Variables

See [defaults/main.yml](./defaults/main.yml). The service accounts and the broker's SSH key path are left to faramir's own defaults, so they are not knobs here.
