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

The development checks need Docker, Bash, Git, Make and Python 3 for archive-header validation.
Pinned stock Python 3.14 and Node 24.22.2 containers install the check dependencies in disposable scratch space.

## Usage

Every root `.yml` except `requirements.yml` is a playbook with a [make](Makefile) target of the same name.
[bin/playbook.py](bin/playbook.py) runs it.

```bash
make help                                        # List the targets
make desktop                                     # Run a playbook
make desktop -- --tags alacritty --limit example # Forward arguments to ansible-playbook
make faramir ARGS="--extra-vars k=v"             # An argument containing "=" or whitespace goes in ARGS
```

| Behaviour           | Detail                                                                                                                                                                                                                                                                                                                                                                                            |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| First goal only     | Most groups share a target's name, so `make base -- --limit desktop` applies `base` alone                                                                                                                                                                                                                                                                                                         |
| ansible-core floor  | An `ansible-playbook` older than 2.19 stops the run                                                                                                                                                                                                                                                                                                                                               |
| Host listing        | An inventory error, or a `--limit` matching no host, stops the run before any prompt                                                                                                                                                                                                                                                                                                              |
| Reachability probe  | Hosts that do not answer SSH within 1s are dropped and named. `PREFLIGHT=none` skips it                                                                                                                                                                                                                                                                                                           |
| Exit status         | The playbook's own, also when the probe dropped a host; `75` when it dropped every host and nothing ran. Through make every failure exits 2                                                                                                                                                                                                                                                       |
| `--ask-become-pass` | Added when the run may reach the controller. `ASK_PASS=1` forces it; a root run never gets it                                                                                                                                                                                                                                                                                                     |
| Credentials         | Every playbook runs under `sops exec-env` when the invoking account can read the store. Those including [tasks/require_credentials.yml](tasks/require_credentials.yml) require it, refusing when it does not exist and re-entering as root when the operator cannot read it. The rest run without it, warning only when the store is readable but sops cannot decrypt it. `SECRETS=none` skips it |
| umask               | `002`, so files created in a setgid share stay group-writable                                                                                                                                                                                                                                                                                                                                     |

A fresh checkout on the controller needs, in order:

1. `hosts` ([Inventory](#inventory)): the controller in `faramir` and `faramir_controller`, and `primary_user` in
   `[all:vars]`, the account the broker and the user-scoped roles install for.
1. `host_vars/<host>.yml` for each Ubuntu host, setting `msmtp_domain` and `msmtp_user`.
1. `faramir.env` in the repository root, listing `msmtp_password` and, if used, `github_token`, one bare name per
   line ([Secrets](#secrets)). Every target stops without it.
1. `make faramir`, unprivileged: installs sops and the broker, and creates the secrets directory and age key but no
   store.
1. Log out and back in: the run adds you to the `dev` group, which the broker's socket requires.
1. `sudo faramir vault add ansible-ctrl`: creates the store in an editor. Add `msmtp_password: <value>`, and
   `github_token` if `faramir.env` names it.
1. `faramir doctor` and `faramir refs`, which should list every name in `faramir.env`.
1. The first-run targets below for the controller, `make faramir` having already run.

A new host needs, before its first run:

- An inventory line naming its `ansible_host`, `ansible_port` and `ansible_user`, and its groups.
- The operator's public key in that account's `~/.ssh/authorized_keys`: [ansible.cfg](ansible.cfg) allows public-key
  authentication only.
- sudo for that account.

Its first run is these targets, in order:

1. `make faramir -- --limit <host>,faramir_controller`: authorizes the broker's key on the host and writes its
   NOPASSWD sudoers entry. The controller must be in the run, and the one become password it asks for is used on
   both hosts, so they must match.
1. `make base`, `make docker`, `make msmtp` and `make dev`, each with `-- --limit <host>`, where the host is in the
   playbook's groups. `dev` comes before `desktop`, whose builds need its toolchains.
1. Every other playbook whose groups hold the host, with `-- --limit <host>`.

After adding a torrent host, run `make torrent -- --limit faramir_controller` to regenerate the controller's transfer
scripts for it.

Tags that are not playbooks run through the playbook that owns them, e.g. `make dev -- --tags ai_maintainer`.

`slow` marks the source builds and installs that take over a minute, and the tasks that need their output.
`-- --skip-tags slow` leaves a host's existing builds as they are.

## Playbooks

| Playbook                                 | Hosts                                 | Role                                                                                                    | Purpose                                                            |
| ---------------------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| [base.yml](base.yml)                     | `all:!routers`                        | [base](roles/base/README.md)                                                                            | Base packages and system configuration                             |
| [desktop.yml](desktop.yml)               | `desktop`                             | [desktop](roles/desktop/README.md), then [bspwm](roles/bspwm/README.md) or [niri](roles/niri/README.md) | Desktop, browser, fonts, and the host's `desktop_environment`      |
| [dev.yml](dev.yml)                       | `dev`                                 | [dev](roles/dev/README.md)                                                                              | Development tools and languages                                    |
| [docker.yml](docker.yml)                 | `dev`, `homeautomation`, `webservers` | [docker](roles/docker/README.md)                                                                        | Docker CE and Compose                                              |
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

`hosts` and `host_vars/<host>.yml` are gitignored. Override role defaults (`roles/<role>/defaults/main.yml`) in
`host_vars/`. Every host names its address, port and login: root's cron and the broker do not read `~/.ssh/config`.

```ini
controller ansible_host=controller.example.com ansible_port=22 ansible_user=andornaut ansible_connection=local ansible_local_become_success_timeout=120
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
and [age](https://github.com/FiloSottile/age)). `faramir.env` (gitignored) lists their names, and each injected one
becomes a variable of that name. Map one to a differently named variable in `host_vars/`:

```yaml
homeautomation_esphome_password: "{{ esphome_password_example_site }}"
```

To add one: put the value in the store (`sudo faramir vault edit ansible-ctrl`, or `sudo faramir vault add
ansible-ctrl` while there is none), its name in `faramir.env`, and a mapping in `host_vars/` if needed.

| Gotcha                              | Detail                                                                                                               |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Injected names outrank `host_vars/` | A `host_vars/` entry under a name `faramir.env` declares is silently replaced. Give a per-host override its own name |
| `faramir.env` must exist            | A checkout without it stops the run. Run ad-hoc `ansible` commands from the repository root                          |
| `vars_plugins_enabled`              | [ansible.cfg](ansible.cfg) must keep `host_group_vars` in the list, or `host_vars/` stops loading                    |

Credentials reach a play through `make` (under sops), the broker
(`faramir run --env-file faramir.env -- ansible-playbook <playbook>.yml --limit '!faramir_controller'`), or the
certificate renewal cron. That `--limit` does not stop a task delegated to `localhost` with `become` (`games`'s
`retroid` tag, `base`'s lockdown when it moves an SSH port) from taking the controller's sudo; run those through
`faramir run -- sudo make <playbook>`.

### GitHub API token

Optional. Without it, GitHub allows 60 API requests an hour per address, shared across the NAT; with it, 5000.

1. Create a fine-grained token with repository access _Public repositories_ and no permissions.
1. `sudo faramir vault edit ansible-ctrl` and add it as `github_token`.
1. Add `github_token` to `faramir.env`.

An expired token fails with HTTP 401. Don't reuse the `gh` CLI's token: it carries your full scopes and lives in the
keyring, where `faramir link` can't read it.

## Secret broker

[faramir](https://github.com/andornaut/faramir) runs credentialed commands without plaintext values reaching a
coding agent. See the [faramir role](roles/faramir/README.md).

`make faramir` installs sops and the broker, and authorizes the broker's key and NOPASSWD sudo across the fleet.
Check with `faramir doctor`, `faramir status` and `faramir refs`, and end to end per
[Verification](roles/faramir/README.md#verification).

## Development

```bash
make check                                     # Full local gate (also the default)
make lint                                      # Static checks in a container
make test                                      # Unit and task-identity checks in a container
make clean                                     # Remove local tooling and git hooks
```

`make check` runs all seven native checks from one sanitized source snapshot. Dependency preparation has network
access; actual checks run offline as UID 19001 with CPU, memory, file-descriptor and time limits. The checkout is
read-only, and work, dependencies and caches live in disposable container scratch space. Host home directories,
Docker sockets and Git metadata are not mounted. A source change during verification discards the result.

Python runs Ansible lint, configuration validation, Ruff, task identity and unit tests. Its separate shell check
renders Jinja templates before checking original and rendered scripts with the pinned ShellCheck wheel. Node runs
Markdown lint from the root npm lockfile. The four Galaxy collections in `requirements.yml` have no version pins;
preparation resolves them for that run, so they are not a frozen dependency graph.

`tests/container/check-stock` coordinates the stock images through the private isolation library.
`tests/container/check` bootstraps Python dependencies and executes native arguments. This project has no build artifact.

| Check          | Covers                                                                                                                                   |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `ansible-lint` | Ansible content                                                                                                                          |
| `config`       | `ansible.cfg` keys, since ansible ignores ones it does not recognize                                                                     |
| `shell`        | shellcheck on every shell script, templates rendered first                                                                               |
| `python`       | `ruff check` and `ruff format --check`                                                                                                   |
| `identity`     | Every task that can change a host declares the account it runs as; read-only modules are exempt ([tests/identity.py](tests/identity.py)) |
| `dispatch`     | Every `tests/test_*.py` but `test_identity.py`                                                                                           |
| `markdown`     | markdownlint on every `.md` file git does not ignore                                                                                     |

WORKAROUND: the Markdown CLI dependency overrides select patched Markdownlint and KaTeX versions for
[GHSA-gg6h-894w-4m9c](https://github.com/advisories/GHSA-gg6h-894w-4m9c) and
[GHSA-238p-pmpm-9mq7](https://github.com/advisories/GHSA-238p-pmpm-9mq7). Remove the overrides when the CLI
requires patched versions itself.

CI ([.github/workflows](.github/workflows)) also runs:

- **`check`**: applies each Ubuntu playbook whose paths changed to the runner from role defaults
  ([tests/check/inventory.yml](tests/check/inventory.yml)), skipping the tasks tagged `slow` so each entry fits in
  five minutes. `faramir`, `torrent`, `router`, `nas`, `rsnapshot` and `upgrade` are not covered, nor are the
  `bspwm` and `niri` roles.
- **`ai-attributions`**: rejects commits carrying AI attribution or long dashes, and agent instruction files.
