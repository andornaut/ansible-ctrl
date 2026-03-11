# ansible-ctrl

Provision workstations and servers using [Ansible](https://www.ansible.com/).

## Requirements

- [Ansible](https://www.ansible.com/) >= 2.14.6
- Ubuntu >= 22.04

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
  help                  - Show this help message
  clean                 - Remove temporary role files
  requirements          - Install required Ansible roles and collections

Playbook targets:
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
  ai-maintainer         - Configure automated GitHub repository maintenance
  rsnapshot             - Configure rsnapshot backup
  upgrade               - Run system upgrades
  webservers            - Configure web servers

# Run specific tasks by tag:
ansible-playbook --ask-become-pass desktop.yml --tags alacritty
ansible-playbook --ask-become-pass dev.yml --tags hobbies
```

## Troubleshooting

Upgrade all collections:

```bash
ansible-galaxy collection install --upgrade -r requirements.yml
```
