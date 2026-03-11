# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is an Ansible-based infrastructure-as-code repository for provisioning workstations, desktop environments, and home servers (Home Assistant/Frigate NVR, NAS, web servers, backup systems). It uses a role-based architecture where each role is responsible for a specific system component or application.

## Commands

### Running Playbooks

```bash
# Install/upgrade required Ansible roles and collections
make requirements

# Workstation roles
make base                   # Base system configuration
make bspwm                  # BSPWM window manager
make desktop                # Desktop environment
make dev                    # Development tools
make docker                 # Docker and Kubernetes
make games                  # Gaming packages
make hobbies                # Hobby tools (3D printing, electronics, FPV)
make msmtp                  # Email forwarding
make niri                   # Niri compositor

# Server roles
make homeautomation         # Home automation
make nas                    # Network Attached Storage
make rsnapshot              # Rsnapshot backup system
make upgrade                # System upgrades
make webservers             # Web servers with Let's Encrypt

# Run specific tasks by tag
ansible-playbook --ask-become-pass desktop.yml --tags alacritty
ansible-playbook --ask-become-pass dev.yml --tags hobbies
```

### Testing and Development

```bash
# Check playbook syntax
ansible-playbook --syntax-check <playbook>.yml

# Dry run (check mode)
ansible-playbook --ask-become-pass --check <playbook>.yml

# Run with increased verbosity
ansible-playbook --ask-become-pass -vvv <playbook>.yml

# List all tasks that would be executed
ansible-playbook --list-tasks <playbook>.yml

# List all tags
ansible-playbook --list-tags <playbook>.yml
```

## Architecture

### Playbook Organization

Each role has a corresponding playbook in the root directory (e.g., `desktop.yml`, `docker.yml`). Playbooks are simple wrappers that run a single role against the appropriate host group.

### Role Structure

Roles follow standard Ansible structure:
- `roles/<role>/tasks/main.yml`: Entry point that imports other task files
- `roles/<role>/tasks/<feature>.yml`: Feature-specific tasks, each tagged for selective execution
- `roles/<role>/defaults/main.yml`: Configurable variables with sensible defaults
- `roles/<role>/templates/`: Jinja2 templates for configuration files

Key roles:

- **base**: Foundation system configuration (from external GitHub repo: andornaut/ansible-role-base)
- **desktop**: Desktop environment with 17 task modules including:
  - Display managers (lightdm, ly, lemurs with conflict prevention)
  - Applications (Firefox, Chrome, Alacritty terminal)
  - Window manager tools (Rofi, Dunst, Eww)
  - System customizations (themes, fonts, dconf settings, GRUB, pavolume)
  - Desktop apps (Insync, LACT GPU control)
- **bspwm**: Binary Space Partitioning Window Manager setup with configuration files
- **niri**: Niri compositor with Wayland/Hyprland tools and Xwayland support
- **dev**: Development tools with 12 task modules:
  - IDEs (Claude, Cursor, VSCode, Codex)
  - Language support (Python, Ruby, Rust, JavaScript)
  - AI tools (Gemini CLI)
  - Utilities (Delta diff viewer, VirtualBox)
- **docker**: Docker Engine and Kubernetes (kubectl, helm, k9s) setup
- **games**: Gaming packages and Flatpaks (Steam, Lutris, emulators)
- **hobbies**: Hobby and maker tools:
  - 3D printing (OrcaSlicer)
  - Electronics (Kicad PCB design)
  - FPV drones (Betaflight Configurator, ExpressLRS Configurator)
- **homeautomation**: Docker-based home automation stack with 17 task modules:
  - Core services (Home Assistant, Frigate NVR, ESPHome, Mosquitto MQTT)
  - Smart home protocols (Matter, Thread Border Router, Bluetooth)
  - Voice assistants (Piper, Whisper, Wyoming Protocol)
  - LLM integration (llama.cpp, Extended OpenAI Conversation)
  - GPU acceleration (Memryx support)
  - Customizations (custom components, themes, www files)
- **nas**: Network Attached Storage configuration with mount points
- **rsnapshot**: Automated backup system with rsnapshot and cron scheduling
- **msmtp**: Email forwarding configuration for system notifications
- **letsencrypt-nginx**: Nginx web server with Let's Encrypt SSL, basic auth, and static site hosting

### Important Architectural Patterns

#### Display Manager Conflict Prevention

The desktop role enforces that only ONE display manager can be installed at a time (lightdm, ly, or lemurs). This is validated using assertions in `roles/desktop/tasks/main.yml` before any installation occurs.

#### mDNS Service Conflict Prevention

The homeautomation role prevents conflicts between Avahi and Matter/Thread services (both provide mDNS) when using `network_mode: host`. See `roles/homeautomation/tasks/main.yml` for validation logic.

#### Docker Network Isolation

The homeautomation role creates a shared bridge network (`homeautomation_default`) that all services connect to. The Home Assistant container must be provisioned first as it creates this network.

#### Task Tagging System

Tasks are extensively tagged to allow selective execution. Tags match either:

- Role names (e.g., `desktop`, `dev`)
- Specific features (e.g., `alacritty`, `firefox`, `hobbies`, `docker`)
- Service groups (e.g., `customizations`, `display-manager`)

Examples:

```bash
# Run only Firefox configuration tasks
ansible-playbook --ask-become-pass desktop.yml --tags firefox

# Run only Python development tools
ansible-playbook --ask-become-pass dev.yml --tags python

# Run only Frigate NVR service
ansible-playbook --ask-become-pass homeautomation.yml --tags frigate
```

#### Modular Task Organization

Most complex roles use a modular structure where `tasks/main.yml` imports feature-specific task files:

**desktop role** (17 modules):

- `apt.yml` - Base package installation
- `alacritty.yml`, `firefox.yml`, `chrome.yml` - Application configuration
- `lightdm.yml`, `ly.yml`, `lemurs.yml` - Display manager options
- `rofi.yml`, `dunst.yml`, `eww.yml` - Window manager utilities
- `themes.yml`, `fonts.yml`, `dconf.yml` - Desktop customization
- `grub.yml`, `pavolume.yml`, `insync.yml`, `lact.yml` - System utilities

**homeautomation role** (17 modules):

- `docker_homeassistant.yml` - Core Home Assistant container (must run first)
- `docker_frigate.yml`, `docker_esphome.yml` - Smart home services
- `docker_matter.yml`, `otbr.yml` - Thread/Matter support
- `docker_voice.yml` - Voice assistant services
- `docker_llm.yml` - LLM integration (llama.cpp)
- `avahi.yml`, `bluetooth.yml`, `mosquitto.yml` - Infrastructure services
- `custom_components.yml`, `themes.yml`, `www.yml` - Customizations

**dev role** (12 modules):

- `claude.yml`, `cursor.yml`, `vscode.yml`, `codex.yml` - IDEs
- `python.yml`, `ruby.yml`, `rust.yml`, `javascript.yml` - Language toolchains
- `delta.yml`, `gemini.yml` - Developer utilities
- `virtualbox.yml` - Virtualization

### Variable Configuration

Role variables are defined in `roles/<role>/defaults/main.yml` and can be overridden in:
- Inventory file (`hosts`)
- Playbook `vars:` section
- Command-line with `-e` flag

Critical variables often use boolean flags to enable/disable features (e.g., `desktop_install_lightdm`, `homeautomation_install_frigate`).

## Inventory Setup

Create a `hosts` file in the project root. The inventory defines which hosts belong to which groups, determining which playbooks run on which systems.

Example structure:

```ini
# Define individual hosts with connection details
workstation ansible_connection=local ansible_python_interpreter=/usr/bin/python3
remote-laptop ansible_host=laptop.example.com ansible_user=username ansible_python_interpreter=/usr/bin/python3
homeserver ansible_connection=local ansible_python_interpreter=/usr/bin/python3
nasserver ansible_connection=local ansible_python_interpreter=/usr/bin/python3

# Host groups define playbook targeting
[workstations]
workstation
remote-laptop

[homeautomation]
homeserver

[nas]
nasserver
workstation

[rsnapshot]
workstation

[webservers]
homeserver
nasserver

[hobbies]
workstation
```

Key host groups:

- **workstations**: Systems running desktop environments and development tools
- **homeautomation**: Systems running home automation services
- **nas**: Systems configured as Network Attached Storage
- **rsnapshot**: Systems running backup jobs
- **webservers**: Systems hosting web services
- **hobbies**: Systems with hobby tools (3D printing, electronics, FPV)

## Configuration Files

### ansible.cfg

Defines Ansible behavior:

```ini
[defaults]
collections_path = ./collections    # Collections installed locally
display_failed_stderr = yes        # Show stderr on failures
inventory = ./hosts                # Default inventory file
nocows = True                      # Disable ASCII art
roles_path = .roles                # External roles installed here
```

### requirements.yml

Defines external dependencies installed via `make requirements`:

**Collections:**

- `community.crypto` - Cryptographic operations and certificate management
- `community.docker` - Docker container and compose management
- `community.general` - General-purpose Ansible modules

**External Roles:**

- `andornaut/ansible-role-base` - Foundation system configuration (downloaded from GitHub)

### Makefile

All Makefile targets automatically run `make requirements` first to ensure dependencies are installed. Each role target runs: `ansible-playbook --ask-become-pass <role>.yml`

Special targets:

- `make help` - Display available targets
- `make clean` - Remove downloaded roles from `.roles/` directory
- `make requirements` - Install/upgrade roles and collections

## Special Playbook Notes

### upgrade.yml

The `upgrade.yml` playbook is unique - it contains inline tasks rather than delegating to a role:

- Updates apt cache and upgrades packages
- Updates flatpak packages
- Can target any host group via inventory

### webservers.yml

The `webservers.yml` playbook combines role execution with inline cron job configuration:

- Executes the `letsencrypt-nginx` role
- Adds inline tasks for cron job setup (certbot renewal, log cleanup)

## Development Workflow

### Adding a New Feature to an Existing Role

1. Create a new task file: `roles/<role>/tasks/<feature>.yml`
2. Add task imports to `roles/<role>/tasks/main.yml`
3. Tag tasks with feature-specific tags
4. Define any new variables in `roles/<role>/defaults/main.yml`
5. Test with: `ansible-playbook --ask-become-pass <role>.yml --tags <feature>`

### Creating a New Role

1. Create role structure: `mkdir -p roles/<newrole>/{tasks,defaults,templates,files,handlers,meta}`
2. Create `roles/<newrole>/tasks/main.yml` as entry point
3. Define defaults in `roles/<newrole>/defaults/main.yml`
4. Create playbook: `<newrole>.yml` that targets appropriate host group
5. Add Makefile target for convenience
6. Update inventory with appropriate host group if needed

### Testing Changes

```bash
# Syntax check before running
ansible-playbook --syntax-check <playbook>.yml

# Dry run to see what would change
ansible-playbook --ask-become-pass --check <playbook>.yml

# Run with verbose output for debugging
ansible-playbook --ask-become-pass -vvv <playbook>.yml

# Run specific tasks only
ansible-playbook --ask-become-pass <playbook>.yml --tags <tag>

# List all available tags
ansible-playbook --list-tags <playbook>.yml
```

## External Dependencies

- External role: `andornaut/ansible-role-base` (installed via requirements.yml)
- Collections: `community.crypto`, `community.docker`, `community.general`
- All dependencies installed locally to `./collections/` and `./.roles/`
