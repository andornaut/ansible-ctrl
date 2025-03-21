# ansible-role-rsnapshot

An [Ansible](https://www.ansible.com/) role that provisions and configures [rsnapshot](http://rsnapshot.org/) for automated incremental backups.

## Overview

rsnapshot is a filesystem snapshot utility that uses rsync to create fast incremental backups. This role automates the setup and configuration of rsnapshot backup systems.

## Features

- Automated rsnapshot installation and configuration
- Support for local and remote backups
- MySQL and PostgreSQL database backup support
- Custom backup script integration
- Configurable retention policies
- Automated backup scheduling

## Requirements

- Ansible 2.9 or higher
- rsync installed on source and target systems
- SSH access for remote backups
- Sufficient storage space for backups

## Role Variables

See [default values](./defaults/main.yml) for complete configuration options.

### Key Variables

- `rsnapshot_hosts`: List of hosts to backup (required)
- `rsnapshot_retain`: Retention settings (optional)
  - `daily`: Number of daily backups to keep (default: 7)
  - `weekly`: Number of weekly backups to keep (default: 4)
  - `monthly`: Number of monthly backups to keep (default: 6)

## Example Configuration

```yaml
rsnapshot_hosts:
  - name: example.com
    local: true                    # Local backup (no SSH)
    user: root                     # User for backup operations
    directories:                   # List of directories to backup
      - /etc/
      - /var/docker-volumes/
    scripts:                       # Custom backup scripts
      - command: /usr/local/bin/backupdockerpostgresql
        args: --host root@example.com --container postgresql postgresql.gz

# Optional retention settings
rsnapshot_retain:
  daily: 7
  weekly: 4
  monthly: 6
```

## Usage

1. Configure backup sources and destinations
2. Set retention policies
3. Run the playbook

Example configuration:

```yaml
rsnapshot_hosts:
  - name: example.com
    local: true
    user: root
    directories:
      - /etc/
      - /var/docker-volumes/
```

## Backup Operations

### Manual Backup
