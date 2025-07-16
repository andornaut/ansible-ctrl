# ansible-role-dev

An [Ansible](https://www.ansible.com/) role that installs and configures development tools and programming languages on Ubuntu.

## Usage

```bash
make workstation
# Select "dev" from among the prompts

# Specific tags only:
ansible-playbook --ask-become-pass workstation.yml --tags cursor
ansible-playbook --ask-become-pass workstation.yml --tags hobbies
```

## Overview

This role automates the installation and configuration of various development tools, programming languages, and IDEs. It provides a comprehensive development environment setup with support for multiple languages and tools.

## Features

### Programming Languages

- Go
- JavaScript (via nvm)
- Python (with pip, venv, pipenv)
- Ruby (with chruby and ruby-install)
- Rust

### Development Tools

- Cursor IDE (AI-powered coding)
- Database clients (MySQL, PostgreSQL)
- Git with Delta (enhanced diff viewer)
- Mercurial
- Visual Studio Code (Wayland support)

### Hardware Development

- KiCAD 8.0 (with kikit)
- OrcaSlicer
- VirtualBox (with extensions)

### Utility Tools

- JQ (JSON processor)
- Meld (diff viewer)
- Xephyr (nested X server)

## Requirements

- Ansible 2.9 or higher
- Ubuntu operating system

## Role Variables

See [default values](./defaults/main.yml).

## License

MIT License. See [LICENSE](../../LICENSE) for full details.
