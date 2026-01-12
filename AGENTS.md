# Agent Guide for Ansible Control Repo

## 1. Project Overview
This repository manages personal infrastructure using Ansible. It provisions workstations, home servers (Home Assistant, Frigate, NAS), and web servers.

**Primary Goal**: Idempotent, automated configuration of diverse systems.

## 2. Directory Structure & Key Files
- **Root**: Playbooks (`*.yml`), `Makefile`, `ansible.cfg`.
- **roles/**: Custom roles. Each role (e.g., `desktop`, `dev`) contains:
    - `tasks/`: Main logic. `main.yml` usually imports other task files.
    - `defaults/`: Default variables.
    - `files/`, `templates/`: Static files and Jinja2 templates.
    - `handlers/`: Service restarts/reloads.
- **.roles/**: External roles installed via `requirements.yml`.
- **hosts**: Inventory file (user-managed, git-ignored).

## 3. Operational Workflow
**Always prefer `make` targets over raw `ansible-playbook` commands when possible.**

- **Setup**: `make requirements` (installs deps).
- **Execution**:
    - `make workstation`: Sets up desktop/dev environment.
    - `make homeassistant-frigate`: Deploys HA stack.
    - `make upgrade`: Runs system updates.
- **Granular Execution (Tags)**:
    - Use tags to run specific tasks without running the whole playbook.
    - Example: `ansible-playbook workstation.yml --tags alacritty`

## 4. Coding & Architectural Standards
- **Role Structure**: Keep `tasks/main.yml` clean. It should primarily `import_tasks` from feature-specific files (e.g., `tasks/alacritty.yml`).
- **Tagging**: **CRITICAL**. Every distinct feature or application installation MUST have a tag matching its name.
- **Variables**: Define defaults in `roles/<role>/defaults/main.yml`. Use boolean flags (e.g., `install_feature_x: true`) to control optional steps.
- **Conflict Management**:
    - **Display Managers**: The `desktop` role enforces single display manager installation. Check `roles/desktop/tasks/main.yml`.
    - **Docker/mDNS**: `homeassistant-frigate` handles Avahi/Matter conflicts carefully.
- **Idempotency**: Ensure all tasks can run multiple times without side effects.

## 5. Agent Instructions for Modifications
- **Adding a new app**:
    1.  Create `roles/<role>/tasks/<app>.yml`.
    2.  Add task to install/configure.
    3.  Add tag: `tags: ['<role>', '<app>']`.
    4.  Import in `roles/<role>/tasks/main.yml`.
- **Modifying config**: Check `templates/` for config files. If a static file is used, check `files/`.
- **Testing**: Ask the user to run with `--check` (dry-run) or specific tags to verify changes.

## 6. Contextual Awareness
- `ansible.cfg` defines `roles_path = .roles` for external dependencies.
- `CLAUDE.md` contains detailed architectural notes. Refer to it if unsure about specific constraints.
