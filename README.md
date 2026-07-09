# ansible-ctrl

Provision workstations and servers using [Ansible](https://www.ansible.com/).

## Requirements

- [Ansible](https://www.ansible.com/) >= 2.18
- Ubuntu >= 24.04

### Initial Setup

Install Ansible on Ubuntu via the [Ansible PPA](https://launchpad.net/~ansible/+archive/ubuntu/ansible):

```bash
sudo add-apt-repository --yes --update ppa:ansible/ansible
sudo apt install ansible
```

Create a `hosts` file in the project root (gitignored). Group names match each playbook's `hosts:` field: `desktop`, `dev`, `games`, `hobbies`, `homeautomation`, `nas`, `rsnapshot`, `webservers`. `base.yml`, `msmtp.yml`, and `upgrade.yml` run on `all`.

```ini
example ansible_connection=local ansible_host=example.com ansible_user=andornaut ansible_python_interpreter=/usr/bin/python3

[desktop]
example

[dev]
example
```

### Inventory and host variables

- `hosts` (gitignored): inventory file
- `host_vars/<hostname>.yml` (gitignored): per-host variable overrides: feature flags (`{role}_install_{component}`), Docker image tags, extra volumes, and any host-specific configuration
- Role defaults live in `roles/<role>/defaults/main.yml`; override them in `host_vars/`, not in defaults

### Secrets

Secrets (API tokens, SMTP passwords, Cloudflare tokens, HA long-lived tokens) are stored in `host_vars/` files, which are gitignored. For shared or committed secrets, use [ansible-vault](https://docs.ansible.com/ansible/latest/vault_guide/index.html):

```bash
ansible-vault encrypt host_vars/example.yml
ansible-playbook --ask-vault-pass --ask-become-pass desktop.yml
```

### CI

Pull requests run [ansible-lint](.github/workflows/lint.yml) on the playbooks and roles. Run the same check locally:

```bash
python3 -m venv /tmp/ansible-lint-venv && /tmp/ansible-lint-venv/bin/pip install ansible-lint && /tmp/ansible-lint-venv/bin/ansible-lint
```

## Usage

Each playbook in the project root (every root `.yml` except `requirements.yml`) has a `make` target of the
same name, which installs dependencies first, then runs `ansible-playbook --ask-become-pass <playbook>.yml`.

```bash
# List the targets
make help

# Run a playbook
make desktop

# Run specific tasks by tag
ansible-playbook --ask-become-pass desktop.yml --tags alacritty
ansible-playbook --ask-become-pass hobbies.yml --tags orcaslicer
```

`upgrade.yml` uses no role: it runs apt dist-upgrade and flatpak upgrade.

## Roles

| Role | Purpose |
| --- | --- |
| [bspwm](roles/bspwm/README.md) | BSPWM window manager and X11 utilities |
| [desktop](roles/desktop/README.md) | Desktop environment (display manager, browser, fonts, themes) |
| [dev](roles/dev/README.md) | Development tools and programming languages |
| [docker](roles/docker/README.md) | Docker CE and Compose, optional Kubernetes and Docker Registry |
| [games](roles/games/README.md) | Gaming packages via flatpak |
| [hobbies](roles/hobbies/README.md) | 3D printing, electronics, FPV tools |
| [homeautomation](roles/homeautomation/README.md) | Home Assistant + related Docker containers |
| [letsencrypt_nginx](roles/letsencrypt_nginx/README.md) | NGINX reverse proxy with Let's Encrypt HTTPS |
| [msmtp](roles/msmtp/README.md) | Email forwarding via MSMTP |
| [nas](roles/nas/README.md) | Encrypted BTRFS RAID arrays (LUKS) |
| [niri](roles/niri/README.md) | Niri Wayland compositor and Wayland utilities |
| [rsnapshot](roles/rsnapshot/README.md) | Incremental backups with rsnapshot |

`desktop.yml` applies the [desktop](roles/desktop/README.md) role to the whole `desktop` group, then applies
[bspwm](roles/bspwm/README.md) or [niri](roles/niri/README.md) according to each host's `desktop_environment`
(`bspwm`, `niri`, or `gnome`).

Automated GitHub repo maintenance (ai-maintainer) is a tag in the [dev](roles/dev/README.md) role, not a role
of its own. The `make ai_maintainer` target refers to a playbook that does not exist; run
`ansible-playbook dev.yml --tags ai_maintainer` instead.

## Troubleshooting

Upgrade all collections:

```bash
ansible-galaxy collection install --upgrade -r requirements.yml
```
