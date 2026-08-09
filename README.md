# ansible-ctrl

Provision Ubuntu workstations and servers with [Ansible](https://www.ansible.com/).

## Requirements

- Ubuntu >= 24.04
- Ansible >= 2.18, from the [Ansible PPA](https://launchpad.net/~ansible/+archive/ubuntu/ansible):

  ```bash
  sudo add-apt-repository --yes --update ppa:ansible/ansible
  sudo apt install ansible
  ```

## Usage

Every root `.yml` except `requirements.yml` is a playbook with a [make](Makefile) target of the same name. The target installs dependencies, then runs `ansible-playbook <playbook>.yml`.

```bash
make help                                        # List the targets
make desktop                                     # Run a playbook
make desktop -- --tags alacritty --limit example # Forward arguments to ansible-playbook
make faramir ARGS="--extra-vars k=v"             # Forward an argument containing "="
```

| Rule | Detail |
| --- | --- |
| Arguments after `--` | forwarded to `ansible-playbook` |
| An argument containing `=` | cannot go after `--`: make reads any such word as a variable assignment. Assign `ARGS` instead. |
| `--ask-become-pass` | added only when the run reaches the controller, the one host whose sudo asks: either it is in the play's host list, or a role in the run has a `become` task under `delegate_to: localhost`. A run that is already root never gets one. |
| `ASK_PASS=1` | forces the prompt |
| `SECRETS=none` | skips the `sops exec-env` re-entry, and tells the play the run reads no credential. For a `--tags` run of a secret-bearing playbook that reaches none. |

Tags that are not playbooks run through the playbook that owns them, e.g. `make dev -- --tags ai_maintainer` for the [dev](roles/dev/README.md) role's cron job, gated on `dev_install_ai_maintainer`.

## Roles

| Role | Purpose |
| --- | --- |
| [base](roles/base/README.md) | Base packages and system configuration, applied to every host |
| [bspwm](roles/bspwm/README.md) | BSPWM window manager and X11 utilities |
| [desktop](roles/desktop/README.md) | Desktop environment (display manager, browser, fonts, themes) |
| [dev](roles/dev/README.md) | Development tools and programming languages |
| [docker](roles/docker/README.md) | Docker CE and Compose, optional Kubernetes and Docker Registry |
| [faramir](roles/faramir/README.md) | Secret broker, so an agent can run credentialed commands without seeing the values |
| [games](roles/games/README.md) | Gaming packages via flatpak, and RetroArch (cores, BIOS, settings, playlists) |
| [hobbies](roles/hobbies/README.md) | 3D printing, electronics, FPV tools |
| [homeautomation](roles/homeautomation/README.md) | Home Assistant and related Docker containers |
| [letsencrypt_nginx](roles/letsencrypt_nginx/README.md) | NGINX reverse proxy with Let's Encrypt HTTPS |
| [msmtp](roles/msmtp/README.md) | Email forwarding via MSMTP |
| [nas](roles/nas/README.md) | Encrypted BTRFS RAID arrays (LUKS) |
| [niri](roles/niri/README.md) | Niri Wayland compositor and Wayland utilities |
| [rsnapshot](roles/rsnapshot/README.md) | Incremental backups with rsnapshot |
| [torrent](roles/torrent/README.md) | rtorrent on the remote host, plus torrent scripts and cron jobs on the controller |

Most playbooks apply one role to one group. The exceptions:

| Playbook | Behaviour |
| --- | --- |
| [desktop.yml](desktop.yml) | Applies `desktop` to the whole `desktop` group, then `bspwm` or `niri` per host's `desktop_environment` |
| [docker.yml](docker.yml) | Applies `docker` to `dev`, `homeautomation` and `webservers` in one run |
| [webservers.yml](webservers.yml) | Applies the `letsencrypt_nginx` role, which does not share the playbook's name |
| [faramir_fleet.yml](faramir_fleet.yml) | Uses no role: authorizes the broker's SSH key and a NOPASSWD sudoers entry on the managed hosts |
| [torrent.yml](torrent.yml) | Applies `torrent` to the `torrent` group, and in the same run delegates the `mvt`/`orgt`/`synct`/`unrart` scripts and cron jobs to the controller (the implicit localhost) |
| [upgrade.yml](upgrade.yml) | Uses no role: apt dist-upgrade and flatpak upgrade |

## Inventory

| Path | Contents |
| --- | --- |
| `hosts` (gitignored) | The inventory. Its group names are the `hosts:` field of each playbook |
| `host_vars/<hostname>.yml` (gitignored) | Per-host overrides: feature flags (`{role}_install_{component}`), Docker image tags, extra volumes |
| [vars_plugins/secret_env.py](vars_plugins/secret_env.py) | Turns each `secret_*` environment variable into a variable of the same name |
| `~/.faramir/secrets/ansible-ctrl.sops.yml` (outside this repo) | Every credential value, and nothing else. See [Secrets](#secrets) |
| `roles/<role>/defaults/main.yml` | Role defaults. Override them in `host_vars/`, not here |

```ini
example ansible_connection=local ansible_host=example.com ansible_user=andornaut ansible_python_interpreter=/usr/bin/python3

[desktop]
example

[dev]
example
```

## Secrets

Every credential (API tokens, SMTP passwords, camera RTSP passwords, Home Assistant long-lived tokens) lives in `~/.faramir/secrets/ansible-ctrl.sops.yml`, encrypted with [sops](https://github.com/getsops/sops) and age, and named `secret_<purpose>`. `host_vars/` holds no values, only references:

```yaml
# host_vars/example.yml
msmtp_password: "{{ secret_msmtp_password }}"
```

[vars_plugins/secret_env.py](vars_plugins/secret_env.py) binds the two: every `secret_*` environment variable becomes an inventory variable of the same name. Adding a credential is three edits: the value into the sops file, the `secret://` ref into `faramir.env`, and the reference into `host_vars/`.

A credential that is not in the environment is absent rather than empty, so a task that reads one fails naming it instead of applying a blank and reporting success. Enabling the plugin in [ansible.cfg](ansible.cfg) means naming `host_group_vars` alongside it, because `vars_plugins_enabled` replaces the default list rather than adding to it.

A value only ever reaches a play through the environment. Three paths put it there:

| Path | How |
| --- | --- |
| `make` (root) | `homeautomation`, `msmtp` and `webservers` re-enter under `sops exec-env`; the rest read no credential. Only root can, the store's group holding no human, so a target `make` cannot serve is refused. See the [faramir role](roles/faramir/README.md). |
| [faramir](roles/faramir/README.md) (agent) | `faramir run --env-file faramir.env -- ansible-playbook <playbook>.yml --limit '!faramir'`. `faramir.env` holds `secret://` refs and no values, gitignored because those refs map this repo's variable names onto the store's layout. |
| certificate renewal cron (root) | [roles/letsencrypt_nginx/tasks/cron.yml](roles/letsencrypt_nginx/tasks/cron.yml) runs `ansible-playbook` under `sops exec-env` rather than through `make`, which would leave root-owned files in `.ansible/` inside the operator's home. It names the keeper's age key explicitly, root's own `~` being `/root`. |

Gotchas:

- **The store is in the operator's home and not in this repo.** A powered-off disk then carries neither the ciphertext nor the key, and this repo is public. Being in that home grants its owner nothing: `~/.faramir/secrets` is `2750 root:faramir-secrets`, a group holding no human.
- **Every play that reads a credential asserts one arrived.** They arrive as a set, so `homeautomation.yml`, `msmtp.yml` and `webservers.yml` check in `pre_tasks`. Without it the first task to read one fails with the tasks before it already applied, which for a container means it is removed and not recreated.
- **Nothing under the home is readable before first login**, so a reboot leaves brokered runs failing until then, and a renewal at 03:00 on an unmounted home does not happen. The cron's preflight mails in that case rather than failing quietly.
- **Back up `~/.faramir/` (store and keeper key) and `~/.config/` (operator identity).** None of it is in git, and rsnapshot covers them only if each path is listed for it. Losing the key loses every credential it ever encrypted. This does put the keys and the ciphertext they open in one snapshot.

## Getting started with the secret broker

[faramir](https://github.com/andornaut/faramir) runs commands that need credentials without any plaintext value entering a coding agent's context. Installing it is an operator action against the controller, and Ansible never needs it in order to run. Its own [README](https://github.com/andornaut/faramir#readme) covers what it protects against.

1. **Install sops**, from the [dev](roles/dev/README.md) role: `make dev`. The faramir binary comes from a release, so no checkout and no Go toolchain are needed.
2. **Install the broker**: `make faramir`. It runs `faramir init` as root, so this asks for a sudo password.
3. **Log out and back in.** The install adds you to the `dev` group, and group membership is read at login. Until then the broker refuses your connections.
4. **Check what it loaded** with `faramir doctor`, `faramir status` and `faramir list-secrets` (names, never values). A ref count of zero is a failure: the broker is running and protecting nothing.
5. **Authorize its SSH key on the fleet**: `make faramir_fleet ASK_PASS=1`, the run that establishes the NOPASSWD sudo the others rely on.
6. **Prove the chain end to end**, per [Verification](roles/faramir/README.md#verification). Anything but a `«SECRET:...»` token is a fault, and that table says which.

## Operations

```bash
make lint                  # every check CI gates on
tests/lint.sh syntax       # or one of ansible-lint, syntax, shell, python

# Upgrade all collections, which `make requirements` does not do
ansible-galaxy collection install --upgrade -r requirements.yml

# Remove downloaded roles and collections, and the lint venv
make clean
```

[.github/workflows/lint.yml](.github/workflows/lint.yml) runs on every pull request: `ansible-lint`, `syntax-check`, `shellcheck` (every shell script under `roles/`, discovered by shebang), and `python-syntax` (every Python file under `roles/*/files/`). All four are [tests/lint.sh](tests/lint.sh), which CI calls one check per job and `make lint` calls in full. The gate is the whole file, not the lines a change touched.

`ansible-lint` is not packaged for Ubuntu, so `tests/lint.sh` keeps it in a venv under `.ansible/`, built on first use. CI installs it with `pip` instead and the script uses whichever it finds on `PATH`.
