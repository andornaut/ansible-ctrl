# ansible-ctrl

Provision Ubuntu workstations and servers with [Ansible](https://www.ansible.com/).

## Requirements

- [Ansible](https://www.ansible.com/) >= 2.18
- Ubuntu >= 24.04

Install Ansible from the [Ansible PPA](https://launchpad.net/~ansible/+archive/ubuntu/ansible):

```bash
sudo add-apt-repository --yes --update ppa:ansible/ansible
sudo apt install ansible
```

## Usage

Every root `.yml` except `requirements.yml` is a playbook with a [make](Makefile) target of the same name. The
target installs dependencies, then runs `ansible-playbook --ask-become-pass <playbook>.yml`. Arguments after `--`
are forwarded to `ansible-playbook`.

```bash
# List the targets
make help

# Run a playbook
make desktop

# Forward arguments, such as tags and limits
make desktop -- --tags alacritty --limit example
```

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
| [games](roles/games/README.md) | Gaming packages via flatpak, and RetroArch (cores, BIOS, settings, playlists) |
| [hobbies](roles/hobbies/README.md) | 3D printing, electronics, FPV tools |
| [homeautomation](roles/homeautomation/README.md) | Home Assistant and related Docker containers |
| [letsencrypt_nginx](roles/letsencrypt_nginx/README.md) | NGINX reverse proxy with Let's Encrypt HTTPS |
| [msmtp](roles/msmtp/README.md) | Email forwarding via MSMTP |
| [nas](roles/nas/README.md) | Encrypted BTRFS RAID arrays (LUKS) |
| [niri](roles/niri/README.md) | Niri Wayland compositor and Wayland utilities |
| [rsnapshot](roles/rsnapshot/README.md) | Incremental backups with rsnapshot |

[desktop.yml](desktop.yml) applies the desktop role to the whole `desktop` group, then applies bspwm or niri
according to each host's `desktop_environment`. [upgrade.yml](upgrade.yml) uses no role: it runs apt dist-upgrade
and flatpak upgrade.

## Inventory

- `hosts` (gitignored): the inventory. Its group names are the `hosts:` field of each playbook.
- `host_vars/<hostname>.yml` (gitignored): per-host overrides, such as feature flags
  (`{role}_install_{component}`), Docker image tags, and extra volumes.
- `roles/<role>/defaults/main.yml`: role defaults. Override them in `host_vars/`, not here.

```ini
example ansible_connection=local ansible_host=example.com ansible_user=andornaut ansible_python_interpreter=/usr/bin/python3

[desktop]
example

[dev]
example
```

## Secrets

API tokens, SMTP passwords, and Home Assistant long-lived tokens live in the gitignored `host_vars/` files.
Encrypt shared or committed secrets with [ansible-vault](https://docs.ansible.com/ansible/latest/vault_guide/index.html):

```bash
ansible-vault encrypt host_vars/example.yml
ansible-playbook --ask-vault-pass --ask-become-pass desktop.yml
```

## Operations

```bash
# Lint, the same check pull requests run via .github/workflows/lint.yml
python3 -m venv /tmp/ansible-lint-venv \
    && /tmp/ansible-lint-venv/bin/pip install ansible-lint \
    && /tmp/ansible-lint-venv/bin/ansible-lint

# Upgrade all collections, which `make requirements` does not do
ansible-galaxy collection install --upgrade -r requirements.yml

# Remove downloaded roles and collections
make clean
```
