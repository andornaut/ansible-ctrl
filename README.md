# ansible-ctrl

[![Test](https://github.com/andornaut/ansible-ctrl/actions/workflows/test.yml/badge.svg)](https://github.com/andornaut/ansible-ctrl/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/license/MIT)

Provision Ubuntu workstations and servers with [Ansible](https://www.redhat.com/en/ansible-collaborative).

| Term       | Meaning                                                                                                         |
| ---------- | --------------------------------------------------------------------------------------------------------------- |
| controller | The host Ansible runs from, and the only member of `faramir_controller`. The only host whose sudo prompts       |
| fleet      | Every other Ubuntu host, reached over SSH with NOPASSWD sudo                                                    |
| `faramir`  | Every host running the secret broker, the controller included                                                   |
| `routers`  | The pfSense routers. FreeBSD, so Ubuntu-only plays are `all:!routers` and [router.yml](router.yml) reaches them |

## Requirements

Ubuntu >= 24.04 and Ansible >= 2.19 from the [Ansible PPA](https://launchpad.net/~ansible/+archive/ubuntu/ansible):

```bash
sudo add-apt-repository --yes --update ppa:ansible/ansible
sudo apt install ansible
```

`make lint` also needs `python3-venv` and Node.js >= 24.21 with npm.

## Usage

Every root `.yml` except `requirements.yml` is a playbook with a [make](Makefile) target of the same name.
[bin/playbook.py](bin/playbook.py) runs it.

```bash
make help                                        # List the targets
make desktop                                     # Run a playbook
make desktop -- --tags alacritty --limit example # Forward arguments to ansible-playbook
make faramir ARGS="--extra-vars k=v"             # An argument containing "=" goes in ARGS
```

| Behaviour           | Detail                                                                                                                                                                                          |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| First goal only     | Every group is also a target, so `make base -- --limit desktop` applies `base` alone                                                                                                            |
| Host listing        | An inventory or variables error, or a `--limit` matching no host, stops the run before any prompt, re-entry or escalation                                                                       |
| Reachability probe  | Hosts that do not answer SSH within 1s are dropped through `--limit` and named, before the playbook and again after it. `PREFLIGHT=none` skips it                                               |
| Exit status         | The playbook's own, or `75` when it succeeded but the probe dropped a host. A playbook ended by a signal exits 128 plus its number                                                              |
| `--ask-become-pass` | Added when the run may reach the controller. `ASK_PASS=1` forces it; a root run never gets it                                                                                                   |
| Credentials         | `homeautomation`, `msmtp` and `webservers` run under `sops exec-env`, re-entering as root when the operator cannot read the store. `SECRETS=none` skips that for a `--tags` run that reads none |
| umask               | `002`, so files created in a setgid share stay group-writable                                                                                                                                   |

A new host needs, before its first run:

- An inventory line naming its `ansible_host`, `ansible_port` and `ansible_user`, and its groups.
- The operator's public key in that account's `~/.ssh/authorized_keys`: [ansible.cfg](ansible.cfg) allows public-key
  authentication only.
- sudo for that account.

Its first run is these targets, in order:

1. `make faramir -- --limit <host>,faramir_controller`: authorizes the broker's key on the host and writes its
   NOPASSWD sudoers entry. The controller has to be in the run: the play that authorizes the key reads it from the
   controller in the same run. The run reaches the controller, so it gets `--ask-become-pass`, and the one password
   it asks for is used for sudo on both, so they must match. No later run needs the host's.
1. `make base`, `make docker`, `make msmtp` and `make dev`, each with `-- --limit <host>`, where the host is in the
   playbook's groups. `dev` comes before `desktop`, whose builds need its toolchains.
1. Every other playbook whose groups hold the host, with `-- --limit <host>`.

A play that targets `faramir_controller` alone does not count: `torrent.yml`'s second play configures the controller
on behalf of the torrent hosts, so the controller's first run skips `torrent`. After adding a torrent host, run
`make torrent -- --limit faramir_controller` to regenerate the controller's scripts for it.

Tags that are not playbooks run through the playbook that owns them, e.g. `make dev -- --tags ai_maintainer`.

## Playbooks

| Playbook                                 | Hosts                                 | Role                                                                                                    | Purpose                                                            |
| ---------------------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| [base.yml](base.yml)                     | `all:!routers`                        | [base](roles/base/README.md)                                                                            | Base packages and system configuration                             |
| [desktop.yml](desktop.yml)               | `desktop`                             | [desktop](roles/desktop/README.md), then [bspwm](roles/bspwm/README.md) or [niri](roles/niri/README.md) | Desktop, browser, fonts, and the host's `desktop_environment`      |
| [dev.yml](dev.yml)                       | `dev`                                 | [dev](roles/dev/README.md)                                                                              | Development tools and languages                                    |
| [docker.yml](docker.yml)                 | `dev`, `homeautomation`, `webservers` | [docker](roles/docker/README.md)                                                                        | Docker CE and Compose, optional Kubernetes and registry            |
| [faramir.yml](faramir.yml)               | `faramir`, then `all`                 | [faramir](roles/faramir/README.md)                                                                      | Secret broker, then its SSH key and NOPASSWD sudo on managed hosts |
| [games.yml](games.yml)                   | `games`                               | [games](roles/games/README.md)                                                                          | Gaming flatpaks and RetroArch                                      |
| [hobbies.yml](hobbies.yml)               | `hobbies`                             | [hobbies](roles/hobbies/README.md)                                                                      | 3D printing, electronics, FPV                                      |
| [homeautomation.yml](homeautomation.yml) | `homeautomation`                      | [homeautomation](roles/homeautomation/README.md)                                                        | Home Assistant and related containers                              |
| [msmtp.yml](msmtp.yml)                   | `all:!routers`                        | [msmtp](roles/msmtp/README.md)                                                                          | Mail forwarding                                                    |
| [nas.yml](nas.yml)                       | `nas`                                 | [nas](roles/nas/README.md)                                                                              | Encrypted BTRFS RAID arrays                                        |
| [router.yml](router.yml)                 | `routers`                             | [router](roles/router/README.md)                                                                        | pfSense connectivity and resolver health checks                    |
| [rsnapshot.yml](rsnapshot.yml)           | `rsnapshot`                           | [rsnapshot](roles/rsnapshot/README.md)                                                                  | Incremental backups                                                |
| [torrent.yml](torrent.yml)               | `torrent`, then `faramir_controller`  | [torrent](roles/torrent/README.md)                                                                      | rtorrent, plus its transfer scripts on the controller              |
| [upgrade.yml](upgrade.yml)               | `all:!routers`                        | none                                                                                                    | apt dist-upgrade and flatpak upgrade                               |
| [webservers.yml](webservers.yml)         | `webservers`                          | [letsencrypt_nginx](roles/letsencrypt_nginx/README.md)                                                  | NGINX reverse proxy with Let's Encrypt                             |

## Inventory

`hosts` and `host_vars/<host>.yml` are gitignored. Role defaults are in `roles/<role>/defaults/main.yml`; override
them in `host_vars/`. Every host names its address, port and login, because root's cron and the broker do not read
`~/.ssh/config`:

```ini
controller ansible_host=controller.example.com ansible_port=22 ansible_user=andornaut ansible_connection=local
example ansible_host=example.com ansible_port=22 ansible_user=andornaut

[faramir]
controller

[faramir_controller]
controller

[desktop]
example

[all:vars]
primary_user=andornaut
```

Define no `localhost` host: some tasks delegate to the implicit one, and a defined one joins every
`hosts: all` play.

## Secrets

Credential values live in `~/.config/faramir/secrets/ansible-ctrl.sops.yml` ([sops](https://github.com/getsops/sops)
and [age](https://github.com/FiloSottile/age)). `faramir.env` (gitignored) lists their names, and
[vars_plugins/faramir_env.py](vars_plugins/faramir_env.py) turns each injected one into a variable of that name.
Map a credential to a differently named variable in `host_vars/`:

```yaml
homeautomation_esphome_password: "{{ esphome_password_example_site }}"
```

To add one: put the value in the store, its name in `faramir.env`, and a mapping in `host_vars/` if needed.

| Gotcha                              | Detail                                                                                                                                                     |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Injected names outrank `host_vars/` | A `host_vars/` entry under a name `faramir.env` declares is silently replaced. Give a per-host override its own name                                       |
| `faramir.env` must exist            | A checkout without it stops the run. Ad-hoc `ansible` commands must run from the repository root to find it                                                |
| `vars_plugins_enabled`              | [ansible.cfg](ansible.cfg) must keep `host_group_vars` in the list, or `host_vars/` stops loading                                                          |
| Credentials arrive as a set         | Plays that read one assert up front ([tasks/require_credentials.yml](tasks/require_credentials.yml)), so a run without them fails before changing anything |

Credentials reach a play three ways: `make` (under sops), the broker
(`faramir run --env-file faramir.env -- ansible-playbook <playbook>.yml --limit '!faramir_controller'`), and the
certificate renewal cron, which runs `make webservers` as root.

### GitHub API token

Optional. Without it, GitHub allows 60 API requests an hour per address, shared across the NAT; with it, 5000.

1. Create a fine-grained token with repository access _Public repositories_ and no permissions.
1. `sudo faramir vault edit ansible-ctrl` and add it as `github_token`.
1. Add `github_token` to `faramir.env`.

Only brokered runs and the credential-reading `make` targets receive it. An expired token fails with HTTP 401.
Don't reuse the `gh` CLI's token: it carries your full scopes and lives in the keyring, where `faramir link` can't
read it.

## Secret broker

[faramir](https://github.com/andornaut/faramir) runs credentialed commands without plaintext values reaching a
coding agent. See the [faramir role](roles/faramir/README.md).

1. `make faramir`: installs sops and the broker, and authorizes the controller's key and NOPASSWD sudo across the
   fleet. Run it before any target that reads a credential.
1. Log out and back in to pick up the `dev` group.
1. Check with `faramir doctor`, `faramir status` and `faramir refs`.
1. Verify end to end per [Verification](roles/faramir/README.md#verification).

## Development

```bash
make lint                                                        # Every check CI runs
tests/lint.sh identity                                           # One check
ansible-galaxy collection install --upgrade -r requirements.yml # Upgrade collections
make clean                                                       # Remove collections and lint tooling
```

| Check          | Covers                                                                                                                                              |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ansible-lint` | Ansible content                                                                                                                                     |
| `config`       | `ansible.cfg` keys, since ansible ignores ones it does not recognize                                                                                |
| `shell`        | shellcheck on every shell script, templates rendered first                                                                                          |
| `python`       | `ruff check` and `ruff format --check`                                                                                                              |
| `identity`     | Every task declares the account it runs as ([tests/identity.py](tests/identity.py))                                                                 |
| `dispatch`     | Unit tests of [bin/playbook.py](bin/playbook.py), the [Makefile](Makefile)'s argument forwarding and [tests/check_matrix.py](tests/check_matrix.py) |
| `markdown`     | markdownlint on every `.md` file git does not ignore                                                                                                |

CI ([.github/workflows](.github/workflows)) also runs:

- **`check`**: applies each Ubuntu playbook to the runner from role defaults
  ([tests/check/inventory.yml](tests/check/inventory.yml)), then runs it again under `--check --diff`. `faramir`,
  `torrent`, `router`, `nas`, `rsnapshot` and `upgrade` are not covered. Only the playbooks whose paths changed
  run ([tests/check_matrix.py](tests/check_matrix.py)): since a pull request's base, or for a push since the last
  commit a run passed on, so a cancelled or failed run's changes are checked again. A shared path, such as base's
  shared task files or `ansible.cfg`, runs them all.
- **`ai-attributions`**: rejects commits carrying AI attribution or long dashes, and agent instruction files.
