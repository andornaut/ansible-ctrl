# ansible-ctrl

[![CI](https://github.com/andornaut/ansible-ctrl/actions/workflows/test.yml/badge.svg)](https://github.com/andornaut/ansible-ctrl/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/license/MIT)

Provision Ubuntu workstations and servers with [Ansible](https://www.ansible.com/).

## Terms

| Term | Meaning |
| --- | --- |
| controller | The host Ansible runs from. Also a managed host, the only one whose sudo prompts, and the only member of the `faramir_controller` group |
| fleet | Every other Ubuntu inventory host, reached over SSH with NOPASSWD sudo |
| `faramir` | Every host running the secret broker. The controller is one of them, and gets what the rest have no use for: the checkout enrolled, and a key the fleet authorizes |
| `routers` | The pfSense routers, one per site. FreeBSD, so no role installs to them and the Ubuntu-only plays are written `all:!routers`. `faramir.yml`'s fleet play does reach them, as `root` |

## Requirements

- Ubuntu >= 24.04
- Ansible >= 2.18, from the [Ansible PPA](https://launchpad.net/~ansible/+archive/ubuntu/ansible):

  ```bash
  sudo add-apt-repository --yes --update ppa:ansible/ansible
  sudo apt install ansible
  ```

## Usage

Every root `.yml` except `requirements.yml` is a playbook with a [make](Makefile) target of the same name, which
installs dependencies then runs `ansible-playbook <playbook>.yml`.

```bash
make help                                        # List the targets
make desktop                                     # Run a playbook
make desktop -- --tags alacritty --limit example # Forward arguments to ansible-playbook
make faramir ARGS="--extra-vars k=v"             # Forward an argument containing "="
```

| Rule | Detail |
| --- | --- |
| Arguments after `--` | forwarded to `ansible-playbook` |
| An argument containing `=` | cannot go after `--`: make reads any such word as a variable assignment. Assign `ARGS` instead |
| `--ask-become-pass` | added only when the run reaches the controller, the one host whose sudo asks: either it is in the play's host list, or a role in the run has a `become` task under `delegate_to: localhost` |
| `ASK_PASS=1` | forces the prompt |
| `SECRETS=none` | skips the `sops exec-env` re-entry, for a `--tags` run that reaches no credential |
| `PREFLIGHT=none` | skips the reachability probe, and attempts every host |
| `ALLOW_ROOT=1` | runs `faramir.yml` as root, which is otherwise refused. A root run connects with the broker's key, so the fleet must already authorize it |

Tags that are not playbooks run through the playbook that owns them, e.g. `make dev -- --tags ai_maintainer` for
the [dev](roles/dev/README.md) role's cron job, gated on `dev_install_ai_maintainer`.

## Playbooks and roles

| Playbook | Hosts | Role | Purpose |
| --- | --- | --- | --- |
| [base.yml](base.yml) | `all:!routers` | [base](roles/base/README.md) | Base packages and system configuration |
| [desktop.yml](desktop.yml) | `desktop` | [desktop](roles/desktop/README.md), then [bspwm](roles/bspwm/README.md) or [niri](roles/niri/README.md) per the host's `desktop_environment` | Display manager, browser, fonts and themes, plus the window manager and its X11 or Wayland utilities |
| [dev.yml](dev.yml) | `dev` | [dev](roles/dev/README.md) | Development tools and programming languages |
| [docker.yml](docker.yml) | `dev`, `homeautomation`, `webservers` | [docker](roles/docker/README.md) | Docker CE and Compose, optional Kubernetes and Docker Registry |
| [faramir.yml](faramir.yml) | `faramir`, then `all` | [faramir](roles/faramir/README.md), then its `ssh` entry point (`tasks_from`) | Secret broker on each faramir host, then the controller's SSH key and a NOPASSWD sudoers entry on the managed hosts |
| [games.yml](games.yml) | `games` | [games](roles/games/README.md) | Gaming packages via flatpak, and RetroArch (cores, BIOS, settings, playlists) |
| [hobbies.yml](hobbies.yml) | `hobbies` | [hobbies](roles/hobbies/README.md) | 3D printing, electronics, FPV tools |
| [homeautomation.yml](homeautomation.yml) | `homeautomation` | [homeautomation](roles/homeautomation/README.md) | Home Assistant and related Docker containers |
| [msmtp.yml](msmtp.yml) | `all:!routers` | [msmtp](roles/msmtp/README.md) | Email forwarding via MSMTP |
| [nas.yml](nas.yml) | `nas` | [nas](roles/nas/README.md) | Encrypted BTRFS RAID arrays (LUKS) |
| [rsnapshot.yml](rsnapshot.yml) | `rsnapshot` | [rsnapshot](roles/rsnapshot/README.md) | Incremental backups with rsnapshot |
| [torrent.yml](torrent.yml) | `torrent` | [torrent](roles/torrent/README.md) | rtorrent on the remote host, plus the `mvt`/`orgt`/`synct`/`unrart` scripts and cron jobs on the controller |
| [upgrade.yml](upgrade.yml) | `all:!routers` | none | apt dist-upgrade and flatpak upgrade |
| [webservers.yml](webservers.yml) | `webservers` | [letsencrypt_nginx](roles/letsencrypt_nginx/README.md) | NGINX reverse proxy with Let's Encrypt HTTPS |

## Inventory

| Path | Contents |
| --- | --- |
| `hosts` (gitignored) | The inventory. Its group names are the `hosts:` field of each playbook |
| `host_vars/<hostname>.yml` (gitignored) | Per-host overrides: feature flags (`{role}_install_{component}`), Docker image tags, extra volumes |
| [vars_plugins/faramir_env.py](vars_plugins/faramir_env.py) | Turns each environment variable `faramir.env` names into a variable of the same name |
| `~/.config/faramir/secrets/ansible-ctrl.sops.yml` (outside this repo) | Every credential value, and nothing else. See [Secrets](#secrets) |
| `roles/<role>/defaults/main.yml` | Role defaults. Override them in `host_vars/`, not here |

Every host names its address, port and login rather than leaving them to the operator's ssh config, which
root's cron and the broker's executor do not read. `[all:vars]` sets `primary_user`, the account user-scoped
tasks target.

```ini
example ansible_host=example.com ansible_port=22 ansible_user=andornaut

[desktop]
example

[all:vars]
primary_user=andornaut
```

## Secrets

Every credential lives in `~/.config/faramir/secrets/ansible-ctrl.sops.yml`, encrypted with
[sops](https://github.com/getsops/sops) and [age](https://github.com/FiloSottile/age), and named for
what it is: `msmtp_password`, `hamcp_token_kaon`. `faramir.env` names every one, which is both what the broker
injects and what [vars_plugins/faramir_env.py](vars_plugins/faramir_env.py) reads to decide which environment
variables are credentials. Each arrives as a variable of that name, so `host_vars/` needs an entry only where the
destination is named something else:

```yaml
# host_vars/example.yml
homeautomation_esphome_password: "{{ esphome_password_cybertron }}"
```

That mapping is what routes a site-scoped credential, or one credential to several consumers. A destination whose
name already matches needs nothing: `msmtp_password` is injected and the role reads it.

**An injected name outranks `host_vars/`.** A vars plugin sits above host and group vars, and
[ansible.cfg](ansible.cfg) lists `faramir_env` last, so a `host_vars/` entry under a name `faramir.env` declares is
dead: the injected value silently replaces it. A per-host override needs a name of its own, mapped as above.

**`faramir.env` is gitignored and both routes read it.** A checkout without it stops the run naming the file
rather than reporting every credential undefined, which would read as a broker that is not serving. It is found
beside the playbook, so an ad-hoc `ansible` command, which has no playbook and uses the working directory
instead, has to run from the repository root.

Adding a credential is two edits, three where it needs a mapping: the value into the sops file, the `faramir://`
ref into `faramir.env`, and a reference in `host_vars/` only if the destination is named differently. A value reaches a play only through the environment, by one of three paths:

| Path | How |
| --- | --- |
| `make` (operator) | `homeautomation`, `msmtp` and `webservers` re-enter under `sops exec-env`; the rest read no credential. Once the broker is installed the store stops being readable by the operator, and those targets [re-enter as root](roles/faramir/README.md#running-playbooks) |
| [faramir](roles/faramir/README.md) (agent) | `faramir run --env-file faramir.env -- ansible-playbook <playbook>.yml --limit '!faramir_controller'`. `faramir.env` holds `faramir://` refs and no values, gitignored because those refs map this repo's variable names onto the store's layout |
| certificate renewal cron (root) | [roles/letsencrypt_nginx/tasks/cron.yml](roles/letsencrypt_nginx/tasks/cron.yml) runs `ansible-playbook` under `sops exec-env` rather than through `make`, which would leave root-owned files in `.ansible/` inside the operator's home |

| Gotcha | Detail |
| --- | --- |
| `vars_plugins_enabled` replaces the default list rather than adding to it | [ansible.cfg](ansible.cfg) names `host_group_vars` alongside `faramir_env`, or `host_vars/` stops loading |
| Credentials arrive as a set | `homeautomation.yml`, `msmtp.yml` and `webservers.yml` assert in `pre_tasks` that one did. Without it the first task to read one fails with the tasks before it already applied, which for a container means it is removed and not recreated |

## Getting started with the secret broker

[faramir](https://github.com/andornaut/faramir) runs commands that need credentials without any plaintext value
entering a coding agent's context. Installing it is an operator action against the controller; Ansible never
needs it in order to run. Its own [README](https://github.com/andornaut/faramir#readme) covers what it protects
against, and the [faramir role](roles/faramir/README.md) covers this repo's part.

1. `make faramir` installs sops and the broker, then authorizes the controller's SSH key and the NOPASSWD sudo
   the other playbooks rely on. It asks for a sudo password once. The faramir binary comes from a release, so no
   checkout and no Go toolchain are needed. Run it before any target that reads a credential: those re-enter under
   `sops exec-env`, and nothing else here installs sops.
1. Log out and back in: the install adds you to the `dev` group, and group membership is read at login.
1. `faramir doctor`, `faramir status`, `faramir refs` (names, never values). A ref count of zero means the
   broker is protecting nothing.
1. Prove the chain end to end, per [Verification](roles/faramir/README.md#verification).

## Operations

```bash
make lint                  # every check CI gates on
tests/lint.sh syntax       # or one of ansible-lint, syntax, shell, python, identity

# Upgrade all collections, which `make requirements` does not do
ansible-galaxy collection install --upgrade -r requirements.yml

# Remove downloaded roles and collections, and the lint venv
make clean
```

[tests/lint.sh](tests/lint.sh) is what `make lint` runs in full and what [CI](.github/workflows/test.yml) runs on
every branch and pull request. Each check runs even after an earlier one fails, and the gate is the whole repo
rather than the lines a change touched.

| Check | Covers |
| --- | --- |
| `ansible-lint` | the repo. Not packaged for Ubuntu, so the script keeps it in a venv under `.ansible/`, built on first use; CI installs it with `pip` and the script takes whichever is on `PATH` |
| `syntax` | `ansible-config validate -t all`, then `ansible-playbook --syntax-check` per playbook against [tests/inventory.ini](tests/inventory.ini), the real inventory being gitignored |
| `shell` | every tracked shell script, discovered by shebang, wherever it lies. A script under `templates/` is rendered to a temporary copy first, Jinja2 expressions to placeholders |
| `python` | `ruff check` and `ruff format --check` over the whole tree, `ruff.toml` naming the exceptions |
| `identity` | no task leaves its account to the connection: the task or a block around it declares one ([tests/identity.py](tests/identity.py)) |

Two more gates that `make lint` does not run:

| Gate | Covers |
| --- | --- |
| markdownlint, a second step of the same workflow | Every tracked `.md` file, per [.markdownlint-cli2.yaml](.markdownlint-cli2.yaml). Run it locally with `markdownlint-cli2` and no arguments, which reads the same config |
| [.github/workflows/ai-attributions.yml](.github/workflows/ai-attributions.yml) | Fails a push or pull request whose added commits carry an AI attribution |
