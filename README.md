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
| `group_vars/all/vault.yml` (gitignored, ansible-vault encrypted) | Every credential, and nothing else. See [Secrets](#secrets) |
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
tokens) lives in `group_vars/all/vault.yml`, encrypted with
[ansible-vault](https://docs.ansible.com/ansible/latest/vault_guide/index.html) and named
`vault_<purpose>`. `host_vars/` holds no credential values, only references to them:

```yaml
# host_vars/example.yml
msmtp_password: "{{ secret_msmtp_password }}"
```

The split keeps `host_vars/` readable and diffable while the secrets themselves are encrypted at
rest.

`ansible.cfg` sets `vault_password_file` to a `~`-relative path, so playbooks need no
`--ask-vault-pass`. The certificate renewal cron is the exception: it runs `ansible-playbook` as
root and unattended, where a prompt would hang and `~` resolves to `/root`, so
[roles/letsencrypt_nginx/tasks/cron.yml](roles/letsencrypt_nginx/tasks/cron.yml) sets
`ANSIBLE_VAULT_PASSWORD_FILE=~{{ primary_user }}/.private/ansible-vault-password` for that run.

A `vault_password_file` that does not exist is a fatal parse error, not a warning, even though
nothing vaulted is committed, so [.github/workflows/lint.yml](.github/workflows/lint.yml) writes a
dummy one before it runs anything. A fresh clone needs the bootstrap below before any playbook,
lint or syntax check will parse.

```bash
# Add or rotate a secret
ansible-vault edit group_vars/all/vault.yml

# Rotate the vault password itself. --new-vault-password-file is required: without it the
# new password is read from the file ansible.cfg names, so the rekey re-encrypts with the
# password it started with and still reports success.
(umask 077 && cat > ~/.private/ansible-vault-password-new)
ansible-vault rekey --new-vault-password-file ~/.private/ansible-vault-password-new \
    group_vars/all/vault.yml \
    && mv ~/.private/ansible-vault-password-new ~/.private/ansible-vault-password

# Bootstrap a new controller: restore the password from a password manager into the path
# ansible.cfg names, then paste and press Ctrl-D
mkdir -p ~/.private && chmod 0700 ~/.private
(umask 077 && cat > ~/.private/ansible-vault-password) && chmod 0400 ~/.private/ansible-vault-password
```

Both halves need a backup, and neither is in git: the password belongs in a password manager, and
`group_vars/all/vault.yml` is gitignored, so it exists only on the controller's disk. Losing
either one loses every secret.

The [faramir](roles/faramir/README.md) role replaces this arrangement. Afterwards the values live in
`secrets/vault.sops.yml` (sops + age, gitignored), `group_vars/all/vars.yml` maps each name to
`lookup('env', ...)`, and `vault_password_file` comes out of `ansible.cfg`. Variable names do not
change, so `host_vars/` needs no edit. The role's README has the migration runbook.

## Operations

[.github/workflows/lint.yml](.github/workflows/lint.yml) runs four jobs on every pull request: `ansible-lint`,
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
