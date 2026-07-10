# ansible-role-msmtp

Installs and configures [MSMTP](https://marlam.de/msmtp/) for email forwarding on Ubuntu.

## Usage

```bash
make msmtp
```

## Variables

See [defaults/main.yml](./defaults/main.yml).

| Variable | Default | Purpose |
| --- | --- | --- |
| `msmtp_domain` | none | Mail domain, used to build `msmtp_send_all_email_to`. Required |
| `msmtp_user` | none | Upstream SMTP username. Required |
| `msmtp_password_INSECURE` | none | Upstream SMTP password. Required, rendered into `/etc/msmtprc-relay` only |
| `msmtp_host` | `smtp.gmail.com` | Upstream SMTP host |
| `msmtp_port` | `587` | Upstream SMTP port |
| `msmtp_relay_interface` | `127.0.0.1` | Interface `msmtpd` listens on. Must be `127.0.0.1` or `::1` |
| `msmtp_relay_port` | `8025` | Port `msmtpd` listens on. Must be unprivileged (1024 to 65535) |

Set the three required vars per host in `host_vars/` (gitignored). The role asserts that they are defined, and
that the relay interface and port meet the constraints above, before touching anything, because its first real
task uninstalls the host's existing MTA.

## Notes

- Local mail is submitted through `/usr/sbin/sendmail` (from `msmtp-mta`), which reads `/etc/msmtprc`. That file
  must be world-readable, because cron drops privileges to the crontab owner before invoking the MTA, and
  Ubuntu's `msmtp` package is not setgid. So `/etc/msmtprc` holds no credentials: it points at `msmtpd` on the
  relay interface, which relays via `/etc/msmtprc-relay`, where the credentials live.
- The relay port is unprivileged so the daemon needs no `CAP_NET_BIND_SERVICE`. `msmtpd` authenticates nobody,
  so `msmtp_relay_interface` must stay on loopback.
- A systemd drop-in replaces the shipped unit's `DynamicUser=true` with `User=msmtp`, the system user
  `msmtp-mta` creates. This is required, not cosmetic: `msmtp` refuses a config passed with `-C` that contains
  secrets unless the file is owned by the calling euid with no group or other permission bits, and a
  `DynamicUser` UID can never own a file on disk. `/etc/msmtprc-relay` is therefore `msmtp:msmtp` mode `0600`.
  The drop-in also drops the now-dead `CAP_NET_BIND_SERVICE` grants and restores the sandboxing `DynamicUser`
  had implied (`ProtectSystem=strict`, `RestrictSUIDSGID`, `RemoveIPC`), so the daemon cannot rewrite the relay
  config it owns.
- `msmtp` ships an AppArmor profile granting read access to `/etc/msmtprc` but not `/etc/msmtprc-relay`. The
  profile is disabled by default (debconf `msmtp/apparmor`), but the role writes the local rule at
  `/etc/apparmor.d/local/usr.bin.msmtp` regardless, so enforcing it later cannot start bouncing every message.
  Where the profile is enforced, AppArmor is reloaded every run rather than on change.
- msmtpd is restarted on every run, before `/etc/msmtprc` is written. It holds no queue, so the restart is cheap,
  and gating it on a config change would let an interrupted run leave the daemon on its packaged `ExecStart`
  while `/etc/msmtprc` already points at it, relaying mail back into msmtpd.
- msmtp does not queue: if the upstream SMTP server is unreachable, the message is rejected rather than retried.
  Anything that must survive an outage needs a queuing MTA.

## Operations

```bash
# Verify delivery end to end
echo test | mail -s test root
journalctl -u msmtpd -n 20
```
