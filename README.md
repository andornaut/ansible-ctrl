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

Install Ansible on Ubuntu:

```bash
sudo apt-add-repository ppa:ansible/ansible
sudo apt install ansible
```

## Usage

```bash
# Workstation roles
make base                   # Base system configuration
make bspwm                  # BSPWM window manager
make desktop                # Desktop environment
make dev                    # Development tools
make docker                 # Docker and Kubernetes
make games                  # Gaming packages
make msmtp                  # Email forwarding
make niri                   # Niri compositor

# Server roles
make homeassistant-frigate  # Home Assistant with Frigate NVR
make nas                    # Network Attached Storage
make rsnapshot              # Rsnapshot backup system
make upgrade                # System upgrades
make webservers             # Web servers with Let's Encrypt

# Run specific tasks by tag
ansible-playbook --ask-become-pass desktop.yml --tags alacritty
ansible-playbook --ask-become-pass dev.yml --tags hobbies
```

## Troubleshooting

Force upgrade community modules:

```bash
ansible-galaxy collection install --force community.general
```
