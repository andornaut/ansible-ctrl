# ansible-role-docker

An [Ansible](https://www.ansible.com/) role that provisions Docker and related tools on Ubuntu.

## Overview

This role automates the installation and configuration of Docker CE, Docker Compose, Docker Registry, and Kubernetes utilities on Ubuntu systems.

## Features

- Docker CE installation and configuration
- Docker Compose setup
- Docker Registry deployment
- Kubernetes utilities installation

## Requirements

- Ansible 2.9 or higher
- Ubuntu operating system
- Internet connectivity for package installation

## Role Variables

See [default values](./defaults/main.yml).

## Usage

1. Include this role in your playbook
2. Configure the required variables
3. Run your playbook

```yaml
- hosts: servers
  roles:
    - role: docker
```

## License

MIT License. See [LICENSE](../../LICENSE) for full details.
