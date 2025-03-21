# ansible-role-rsnapshot

An [Ansible](https://www.ansible.com/) role that provisions and configures [rsnapshot](http://rsnapshot.org/) for automated incremental backups.

## Overview

rsnapshot is a filesystem snapshot utility that uses rsync to create fast incremental backups. This role:

- Installs and configures rsnapshot
- Sets up automated backup schedules
- Supports both local and remote backups
- Supports backing up MySQL and PostgreSQL databases
- Supports custom backup scripts

## Requirements

- Ansible 2.9 or higher
- rsync installed on both source and target systems (for remote backups)

## Variables

See [default values](./defaults/main.yml) for complete configuration options.

### Key Variables

- `rsnapshot_hosts`: List of hosts to backup (required)
- `rsnapshot_retain`: Retention settings (optional)
  - `daily`: Number of daily backups to keep (default: 7)
  - `weekly`: Number of weekly backups to keep (default: 4)
  - `monthly`: Number of monthly backups to keep (default: 6)

### Example Configuration

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

1. Include this role in your playbook
2. Configure the `rsnapshot_hosts` variable
3. Run your playbook

```yaml
- hosts: backup_servers
  roles:
    - role: rsnapshot
```

## Backup Operations

### Manual Backup

```bash
# Test configuration
rsnapshot configtest

# Dry-run backup
rsnapshot -t daily    # Test daily backup
rsnapshot -t weekly   # Test weekly backup
rsnapshot -t monthly  # Test monthly backup

# Execute backup
rsnapshot daily       # Run daily backup
rsnapshot weekly      # Run weekly backup
rsnapshot monthly     # Run monthly backup
```

### Backup Structure

Backups are stored in the following structure:

```text
/var/cache/rsnapshot/
├── daily.0/
├── daily.1/
├── weekly.0/
├── weekly.1/
├── monthly.0/
└── monthly.1/
```

## Troubleshooting

1. Check rsnapshot configuration:

   ```bash
   rsnapshot configtest
   ```

2. Run backup with verbose logging:

   ```bash
   rsnapshot -v daily
   ```

3. Check logs:

   ```bash
   tail -f /var/log/rsnapshot.log
   ```

## License

MIT
