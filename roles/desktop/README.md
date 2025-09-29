# ansible-role-desktop

An [Ansible](https://www.ansible.com/) role that configures a Linux desktop environment with common applications and settings on Ubuntu.

## Usage

```bash
make workstation
# Select "desktop" from among the prompts

# Specific tags only:
ansible-playbook --ask-become-pass workstation.yml --tags display-manager
ansible-playbook --ask-become-pass workstation.yml --tags firefox
```

## Overview

This role automates the setup and configuration of a complete desktop environment, including common applications, system settings, and user preferences.

## Features

- Desktop environment configuration
- Common application installation
- System settings optimization
- User preference management
- Integration with Linux desktop tools

## Requirements

- Ansible 2.9 or higher
- Ubuntu operating system

## Role Variables

See [default values](./defaults/main.yml).

## Usage

1. Include this role in your playbook
2. Configure the required variables
3. Run your playbook

```yaml
- hosts: workstations
  roles:
    - role: desktop
```

## License

MIT License. See [LICENSE](../../LICENSE) for full details.
