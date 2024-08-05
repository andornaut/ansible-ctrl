# ansible-role-rsnapshot

An [Ansible](https://www.ansible.com/) role that provisions
[rsnapshot](http://rsnapshot.org/) and schedules automated backups.

## Variables

See [default values](./defaults/main.yml).

### Example configuration

```
rsnapshot_hosts:
  - name: example.com
    local: true
    user: root
    directories:
      - /etc/
      - /var/docker-volumes/
    scripts:
      - command: /usr/local/bin/backupdockerpostgresql
        args: --host root@example.com --container postgresql postgresql.gz
```

## Development

```
# Validate rsnapshot.conf
rsnapshot configtest

# Dry-run
interval=daily
#interval=weekly
#interval=monthly
rsnapshot -t ${interval}
```

