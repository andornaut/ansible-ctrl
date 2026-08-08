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
| An argument containing `=` | cannot go after `--`: make reads any such word as a variable assignment, so `-- --extra-vars k=v` forwards a bare `--extra-vars` and ansible exits with a usage message. Assign `ARGS` instead, which overrides the value the target derives from the goals. |
| `--ask-become-pass` | added only when the run reaches the controller, the one host whose sudo asks: either it is in the play's host list, or a role in the run has a `become` task under `delegate_to: localhost`. A run that is already root never gets one. |
| `ASK_PASS=1` | forces the prompt |
| `SECRETS=none` | skips the `sops exec-env` re-entry, for a playbook that needs no credential |

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

[vars_plugins/secret_env.py](vars_plugins/secret_env.py) binds the two: every `secret_*` environment variable becomes an inventory variable of the same name, so there is no per-credential mapping to keep in step with anything. Adding a credential is three edits: the value into the sops file, the `secret://` ref into `faramir.env`, and the reference into `host_vars/`.

A credential that is not in the environment is absent rather than empty, so the first task to use it fails naming it instead of applying a blank credential and reporting success. An empty value counts as absent for the same reason. Enabling the plugin in [ansible.cfg](ansible.cfg) means naming `host_group_vars` alongside it, because `vars_plugins_enabled` replaces the default list rather than adding to it.

A value only ever reaches a play through the environment. Three paths put it there:

| Path | How |
| --- | --- |
| `make` (operator) | wraps itself in `sops exec-env` when the values are not already loaded, using the operator's age identity at `~/.config/sops/age/keys.txt` |
| [faramir](roles/faramir/README.md) (agent) | `faramir run --env-file faramir.env -- ansible-playbook homeautomation.yml --limit '!faramir'`. `faramir.env` holds `secret://` references and no values, and is gitignored because those references map this repo's variable names onto the store's layout. |
| certificate renewal cron (root) | [roles/letsencrypt_nginx/tasks/cron.yml](roles/letsencrypt_nginx/tasks/cron.yml) runs `ansible-playbook` under `sops exec-env` directly rather than through `make`, because every make target depends on the `requirements` stamp and a root cron would leave root-owned files in `.ansible/` inside the operator's home. It names the keeper's age key explicitly, root's own `~` being `/root`. |

Where things live and why:

- **The store is in the operator's home**, alongside the age key that opens it, so a powered-off disk carries neither. The agent runs as the operator and its own age identity is in that home, so moving the store there costs nothing: what confines the agent is mode and uid, not location.
- **Not in this repo.** It is public, so a store inside it is ciphertext of every credential one `git add -f` or one broken ignore rule from publication, which rotating afterwards does not undo.
- **`~/.faramir/secrets` is `2770 root:dev`**, so `sops` edits it in place without sudo, while the keeper reaches it through a unit that sets `ProtectHome=tmpfs` and binds only that one directory back in.
- **Nothing under the home is readable before first login**, so a reboot leaves brokered runs failing until then, and a renewal at 03:00 on an unmounted home does not happen. The cron's preflight mails in that case rather than failing quietly.
- **Back up `~/.faramir/` (store and keeper key) and `~/.config/` (operator identity).** None of it is in git. rsnapshot covers them only if each path is listed for it, and losing the key that opens the store loses every credential it ever encrypted. This does put the keys and the ciphertext they open in the same snapshot.

## Getting started with the secret broker

[faramir](https://github.com/andornaut/faramir) runs commands that need credentials without any plaintext value entering a coding agent's context. Installing it is an operator action against the controller, and Ansible never needs it in order to run. Its own [README](https://github.com/andornaut/faramir#readme) explains what it protects against, which is worth reading before trusting it.

1. **Install sops**, which the [dev](roles/dev/README.md) role provides: `make dev`. The faramir binaries are downloaded from a release, so no faramir checkout and no Go toolchain are needed.
2. **Install the broker**: `make faramir`. It runs `faramir init` as root, so this target asks for a sudo password.
3. **Log out and back in.** The install adds you to the `dev` group and group membership is read at login. Until then the broker refuses your connections.
4. **Check what it loaded.** A ref count of zero is a failure, not a fresh start: the broker is running and protecting nothing.

   ```bash
   faramir doctor          # whether the install is doing its job, not just running
   faramir status          # config path, the sops files it manages, and the ref count
   faramir list-secrets    # the names, never the values
   ```

5. **Authorize its SSH key on the managed hosts**: `make faramir_fleet ASK_PASS=1`. `ASK_PASS=1` is required because this is the run that establishes the NOPASSWD sudo the others rely on.
6. **Prove the chain end to end:**

   ```bash
   faramir run --env-file faramir.env -- \
       ansible <host> -m debug -a 'var=secret_msmtp_password'
   # -> "secret_msmtp_password": "«SECRET:secret_msmtp_password»"
   ```

   Anything else is a fault; the [faramir role](roles/faramir/README.md) says what each one means.

After that, playbooks run through the broker rather than through `make`. `--limit '!faramir'` excludes the controller, which a brokered run cannot configure: commands run as a uid with no sudo there. The controller's own playbooks stay yours to apply.

## Operations

```bash
make lint                  # every check CI gates on
tests/lint.sh syntax       # or one of ansible-lint, syntax, shell, python

# Upgrade all collections, which `make requirements` does not do
ansible-galaxy collection install --upgrade -r requirements.yml

# Remove downloaded roles and collections, and the lint venv
make clean
```

[.github/workflows/lint.yml](.github/workflows/lint.yml) runs on every pull request: `ansible-lint`, `syntax-check`, `shellcheck` (every shell script under `roles/`, discovered by shebang), and `python-syntax` (every Python file under `roles/*/files/`). All four are [tests/lint.sh](tests/lint.sh), which CI calls one check per job and `make lint` calls in full, so what passes locally is what passes there. The gate is the whole file, not the lines a change touched.

`ansible-lint` is not packaged for Ubuntu, so `tests/lint.sh` keeps it in a venv under `.ansible/`, built on first use. CI installs it with `pip` instead and the script uses whichever it finds on `PATH`.
