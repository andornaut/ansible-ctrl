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

Every root `.yml` except `requirements.yml` is a playbook with a [make](Makefile) target of the same name. The
target installs dependencies, then runs `ansible-playbook <playbook>.yml`. Arguments after `--` are forwarded
to `ansible-playbook`.

```bash
make help                                        # List the targets
make desktop                                     # Run a playbook
make desktop -- --tags alacritty --limit example # Forward arguments
```

`--ask-become-pass` is added only when the run reaches the controller, which is the only host whose sudo asks
for a password: either it is in the play's host list, or a role in the run has a `become` task under
`delegate_to: localhost`. `ASK_PASS=1` forces the prompt.

`make ai_maintainer` is the exception: it is a tag in the [dev](roles/dev/README.md) role rather than a playbook,
so the target runs `dev.yml --tags ai_maintainer`.

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
| [faramir_fleet.yml](faramir_fleet.yml) | Uses no role: authorizes the broker's SSH key and a NOPASSWD sudoers entry on the managed hosts |
| [torrent.yml](torrent.yml) | Applies `torrent` to the `torrent` group, and in the same run delegates the `mvt`/`orgt`/`synct`/`unrart` scripts and cron jobs to the controller (the implicit localhost) |
| [upgrade.yml](upgrade.yml) | Uses no role: apt dist-upgrade and flatpak upgrade |

## Inventory

| Path | Contents |
| --- | --- |
| `hosts` (gitignored) | The inventory. Its group names are the `hosts:` field of each playbook |
| `host_vars/<hostname>.yml` (gitignored) | Per-host overrides: feature flags (`{role}_install_{component}`), Docker image tags, extra volumes |
| `secrets/vault.sops.yml` (gitignored, sops encrypted) | Every credential value, and nothing else. See [Secrets](#secrets) |
| `group_vars/all/vars.yml` (gitignored) | Maps each credential name to `lookup('env', ...)`. Holds no values |
| `roles/<role>/defaults/main.yml` | Role defaults. Override them in `host_vars/`, not here |

```ini
example ansible_connection=local ansible_host=example.com ansible_user=andornaut ansible_python_interpreter=/usr/bin/python3

[desktop]
example

[dev]
example
```

## Secrets

Every credential (API tokens, SMTP passwords, camera RTSP passwords, Home Assistant long-lived
tokens) lives in `secrets/vault.sops.yml`, encrypted with [sops](https://github.com/getsops/sops)
and age, and named `secret_<purpose>`. `host_vars/` holds no credential values, only references to
them:

```yaml
# host_vars/example.yml
msmtp_password: "{{ secret_msmtp_password }}"
```

`group_vars/all/vars.yml` binds the two. It maps each name to the environment and holds no value
itself:

```yaml
secret_msmtp_password: "{{ lookup('env', 'secret_msmtp_password') }}"
```

The split keeps `host_vars/` readable and diffable while the values are encrypted at rest, and it
means a value only ever reaches a play through the environment. Two things put it there. `make`
wraps itself in `sops exec-env` when the values are not already loaded, which needs the age
identity at `~/.config/sops/age/keys.txt`. The [faramir](roles/faramir/README.md) broker supplies
the same names to a command that never sees them:

```bash
faramir run --env-file faramir.env -- ansible-playbook homeautomation.yml --limit '!faramir'
```

`faramir.env` is committed, because it maps each environment variable to a `secret://` reference
and holds no values. Adding a credential is four edits: the value into the sops file, the
`lookup('env', ...)` mapping into `group_vars/all/vars.yml`, the ref into `faramir.env`, and the
reference into `host_vars/`.

The certificate renewal cron is the third path, and wraps itself.
[roles/letsencrypt_nginx/tasks/cron.yml](roles/letsencrypt_nginx/tasks/cron.yml) runs
`ansible-playbook` under `sops exec-env` directly rather than through `make`, which would add
`--ask-become-pass` on a run that reaches the controller and leave cron with a prompt and no
terminal. It names the age key explicitly, root's own `~` being `/root`.

The encrypted file lives in `secrets/`, deliberately not under `group_vars/`. Ansible auto-loads
every `.yml` there and a sops file is valid YAML, so it would bind each var to its `ENC[...]`
ciphertext without erroring, and hosts would get the ciphertext as the password.

The encrypted file and the age identity both need a backup, and neither is in git: the identity
belongs in a password manager, and `secrets/vault.sops.yml` is gitignored, so it exists only on the
controller's disk. Losing either one loses every secret.

## Operations

[.github/workflows/lint.yml](.github/workflows/lint.yml) runs on every pull request: `ansible-lint`,
`syntax-check`, `shellcheck` (every shell script under `roles/`, discovered by shebang), and `python-syntax`
(every Python file under `roles/*/files/`). The first two are reproducible locally:

```bash
# Lint
python3 -m venv /tmp/ansible-lint-venv \
    && /tmp/ansible-lint-venv/bin/pip install ansible-lint \
    && /tmp/ansible-lint-venv/bin/ansible-lint

# Syntax-check every playbook. The real inventory is gitignored, so parse against the committed CI one.
for pb in *.yml; do [ "$pb" = requirements.yml ] && continue; \
    ansible-playbook --syntax-check -i tests/inventory.ini "$pb"; done

# Upgrade all collections, which `make requirements` does not do
ansible-galaxy collection install --upgrade -r requirements.yml

# Remove downloaded roles and collections
make clean
```
