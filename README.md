# ansible-ctrl

Provision workstations and servers using [Ansible](https://www.ansible.com/).

## Requirements

- [Ansible](https://www.ansible.com/) >= 2.14.6
- Ubuntu >= 24.04

### Initial Setup

Create a `hosts` file in the project root:

```ini
example ansible_connection=local ansible_host=example.com ansible_user=andornaut ansible_python_interpreter=/usr/bin/python3

[workstations]
example

[upgrade]
example
```

Install Ansible on Ubuntu via the [Ansible PPA](https://launchpad.net/~ansible/+archive/ubuntu/ansible):

```bash
sudo add-apt-repository --yes --update ppa:ansible/ansible
sudo apt install ansible
```

## Usage

```bash
$ make help
Available targets:
  clean                 - Remove temporary role files
  help                  - Show this help message
  requirements          - Install required Ansible roles and collections

Playbook targets:
  ai_maintainer         - Configure automated GitHub repository maintenance
  base                  - Configure base system
  bspwm                 - Configure BSPWM window manager
  desktop               - Configure desktop environment
  dev                   - Configure development tools
  docker                - Configure Docker and Kubernetes
  games                 - Configure gaming packages
  hobbies               - Configure hobby tools (3D printing, electronics, FPV)
  homeautomation        - Configure home automation
  msmtp                 - Configure email forwarding
  nas                   - Configure NAS server
  niri                  - Configure Niri compositor
  rsnapshot             - Configure rsnapshot backup
  upgrade               - Run system upgrades
  webservers            - Configure web servers

# Run specific tasks by tag:
ansible-playbook --ask-become-pass desktop.yml --tags alacritty
ansible-playbook --ask-become-pass hobbies.yml --tags orcaslicer
```

## Roles

| Role | Purpose |
| --- | --- |
| [ai_maintainer](roles/ai_maintainer/) | Automated GitHub repo maintenance via AI agent + cron |
| [bspwm](roles/bspwm/) | BSPWM window manager |
| [desktop](roles/desktop/) | Desktop environment (display manager, browser, fonts, themes) |
| [dev](roles/dev/) | Development tools and programming languages |
| [docker](roles/docker/) | Docker CE, Compose, optional Kubernetes |
| [games](roles/games/) | Gaming packages via flatpak |
| [hobbies](roles/hobbies/) | 3D printing, electronics, FPV tools |
| [homeautomation](roles/homeautomation/) | Home Assistant + related Docker containers |
| [letsencrypt_nginx](roles/letsencrypt_nginx/) | NGINX reverse proxy with Let's Encrypt HTTPS |
| [msmtp](roles/msmtp/) | Email forwarding via MSMTP |
| [nas](roles/nas/) | Encrypted BTRFS RAID arrays (LUKS) |
| [niri](roles/niri/) | Niri Wayland compositor |
| [rsnapshot](roles/rsnapshot/) | Incremental backups with rsnapshot |

## Troubleshooting

Upgrade all collections:

```bash
ansible-galaxy collection install --upgrade -r requirements.yml
```
