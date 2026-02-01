# ansible-role-dev

Installs development tools and programming languages on Ubuntu.

## Usage

```bash
make dev

ansible-playbook --ask-become-pass dev.yml --tags cursor
ansible-playbook --ask-become-pass dev.yml --tags python
ansible-playbook --ask-become-pass dev.yml --tags rust
```

## Features

### Programming Languages

- Go
- JavaScript (via nvm)
- Python (with pip, venv, pipenv)
- Ruby (with chruby and ruby-install)
- Rust

### Development Tools

- Cursor IDE
- Database clients (MySQL, PostgreSQL)
- Git with Delta
- Mercurial
- Visual Studio Code

### Hardware Development

- KiCAD 8.0 (with kikit)
- OrcaSlicer
- VirtualBox

## Variables

See [defaults/main.yml](./defaults/main.yml).
