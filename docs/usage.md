# Run playbooks

## Requirements

Use Ubuntu 24.04 or later and ansible-core 2.19 or later. Install Ansible from the
[Ansible PPA](https://launchpad.net/~ansible/+archive/ubuntu/ansible).

```bash
sudo add-apt-repository --yes --update ppa:ansible/ansible
sudo apt install ansible
```

## Usage

Every root `.yml` except `requirements.yml` is a playbook with a [make](../Makefile) target of the same name.
[bin/playbook.py](../bin/playbook.py) runs it. Run the `make` commands from the repository root.

```bash
make help                                        # List the targets
make desktop                                     # Run a playbook
make desktop -- --tags alacritty --limit example # Forward arguments to ansible-playbook
make faramir ARGS="--extra-vars k=v"             # An argument containing "=" or whitespace goes in ARGS
```

| Behaviour           | Detail                                                                                                                                                                                                                                                                                                                                                                                                      |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| First goal only     | Most groups share a target's name. `make base -- --limit desktop` applies `base` alone                                                                                                                                                                                                                                                                                                                      |
| ansible-core floor  | An `ansible-playbook` older than 2.19 stops the run                                                                                                                                                                                                                                                                                                                                                         |
| Host listing        | An inventory error, or a `--limit` matching no host, stops the run before any prompt                                                                                                                                                                                                                                                                                                                        |
| Reachability probe  | The SSH probe uses a 1-second connection timeout. Unreachable hosts are dropped and named. `PREFLIGHT=none` skips it                                                                                                                                                                                                                                                                                        |
| Exit status         | The playbook's own, even when the probe dropped a host. The wrapper exits `75` when the probe drops every host. Make reports failures as exit status `2`                                                                                                                                                                                                                                                    |
| `--ask-become-pass` | Added when the run may reach the controller. `ASK_PASS=1` forces it for runs as a non-root user                                                                                                                                                                                                                                                                                                             |
| Credentials         | Playbooks including [tasks/require_credentials.yml](../tasks/require_credentials.yml) run under `sops exec-env`. They stop if the store is missing and re-enter as root if the operator cannot read it. Other playbooks use the store if it is readable and sops can decrypt it. They warn and proceed without credentials if it is readable but decryption fails. `SECRETS=none` skips credential handling |
| umask               | `002`, so files created in a setgid share stay group-writable                                                                                                                                                                                                                                                                                                                                               |

### First run on the controller

A fresh checkout on the controller needs these steps in order.

1. `hosts` ([Inventory](inventory.md#inventory)): the controller in `faramir` and `faramir_controller`, and `primary_user` in
   `[all:vars]`, the account the broker and the user-scoped roles install for.
1. `host_vars/<host>.yml` for each Ubuntu host, setting `msmtp_domain` and `msmtp_user`.
1. `faramir.env` in the repository root, listing `msmtp_password` and, if used, `github_token`, one bare name per
   line ([Secrets](secrets.md#secrets)). Every target stops without it.
1. `make faramir`, unprivileged: installs sops and the broker, and creates the secrets directory and age key but no
   store.
1. Log out and back in: the run adds you to the `dev` group, which the broker's socket requires.
1. `sudo faramir vault add ansible-ctrl`: creates the store in an editor. Add `msmtp_password: <value>`, and
   `github_token` if `faramir.env` names it.
1. `faramir doctor` and `faramir refs`, which should list every name in `faramir.env`.
1. The first-run targets below for the controller, `make faramir` having already run.

### First run on a new Ubuntu host

Before its first run, a new host needs the following.

- An inventory line naming its `ansible_host`, `ansible_port` and `ansible_user`, and its groups.
- The operator's public key in that account's `~/.ssh/authorized_keys`: [ansible.cfg](../ansible.cfg) allows public-key
  authentication only.
- sudo for that account.

Run these targets in order.

1. `make faramir -- --limit <host>,faramir_controller`: authorizes the broker's key on the host and writes its
   NOPASSWD sudoers entry. The controller must be in the run, and the one become password it asks for is used on
   both hosts, so they must match.
1. `make base`, `make docker`, `make msmtp` and `make dev`, each with `-- --limit <host>`, where the host is in the
   playbook's groups. `dev` comes before `desktop`, whose builds need its toolchains.
1. Every other playbook whose groups hold the host, with `-- --limit <host>`.

After adding a torrent host, run `make torrent -- --limit faramir_controller` to regenerate the controller's transfer
scripts for it.

### Tags

Run tags through the playbook that owns them, for example `make dev -- --tags ai_maintainer`.

`slow` marks the source builds and installs that take over a minute, and the tasks that need their output.
`-- --skip-tags slow` leaves a host's existing builds as they are.
