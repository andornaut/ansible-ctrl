# ansible-role-msmtp

An [Ansible](https://www.ansible.com/) role that installs and configures [MSMTP](https://marlam.de/msmtp/) (Mini Simple Mail Transfer Protocol) on Ubuntu.

## Overview

MSMTP is a lightweight SMTP client that enables email sending from command line or scripts. This role provides automated installation and configuration of MSMTP.

## Features

- Simple SMTP client installation
- Support for Gmail and other SMTP servers
- TLS/SSL encryption support
- System-wide or per-user configuration
- Integration with system mail commands

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
- hosts: servers
  roles:
    - role: msmtp
```

## License

MIT License. See [LICENSE](../../LICENSE) for full details.
