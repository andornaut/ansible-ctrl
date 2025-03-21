# ansible-ctrl

Provision workstations and servers using [Ansible](https://www.ansible.com/).

## Overview

This repository contains Ansible playbooks for automating the setup and configuration of:

- Workstation and desktop environment: applications, games, tools, etc
- Home Assistant with Frigate
- Network Attached Storage (NAS)
- Email forwarding
- Rsnapshot backup system
- System upgrades
- Web servers

## Requirements

- [Ansible](https://www.ansible.com/) >= 2.14.6
- [Make](https://www.gnu.org/software/make/)
- Ubuntu >= 22.04

### Initial Setup

Create a file named `hosts` in the project root:

```ini
example ansible_connection=local ansible_host=example.com ansible_user=andornaut ansible_python_interpreter=/usr/bin/python3

[upgrade]
example
```

Install or upgrade Ansible on Ubuntu:

```bash
sudo apt remove ansible --purge
sudo apt-add-repository ppa:ansible/ansible
sudo apt install ansible
```

## Available Commands

Run any of the following make commands to execute the corresponding playbook:

```bash
make homeassistant-frigate # Set up Home Assistant with Frigate NVR
make rsnapshot             # Configure Rsnapshot backup system
make upgrade               # Run system upgrades
make webservers            # Configure web servers
make workstation           # Set up workstation/desktop environment
```

### Workstation Setup

The `make workstation` command runs the [workstation](./workstation.yml) playbook, which:

- Prompts you to choose which roles to include
- Configures your development environment
- Sets up common tools and applications

## Development

### Directory Structure

```text
.
├── hosts                # Inventory file (create this)
├── workstation.yml      # Workstation configuration playbook
├── roles/               # Ansible roles
└── Makefile             # Command definitions
```

## Troubleshooting

### Common Issues

1. **Module Bugs**: If you encounter issues with community modules, try forcing an upgrade:

```bash
ansible-galaxy collection install --force community.general
```
