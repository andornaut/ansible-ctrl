# ansible-role-msmtp

Installs and configures [MSMTP](https://marlam.de/msmtp/) for email forwarding on Ubuntu.

## Usage

```bash
make msmtp
```

## Tags

| Tag   | Description                                                |
| ----- | ---------------------------------------------------------- |
| msmtp | Everything in this role; `msmtp.yml` applies it as a whole |

## Variables

See [defaults/main.yml](./defaults/main.yml).

| Variable                   | Purpose                                                                   |
| -------------------------- | ------------------------------------------------------------------------- |
| `msmtp_domain`             | Mail domain, used to build `msmtp_send_all_email_to`. Required            |
| `msmtp_user`               | Upstream SMTP username. Required                                          |
| `msmtp_password`           | Upstream SMTP password. Required, rendered into `/etc/msmtprc-relay` only |
| `msmtp_host`, `msmtp_port` | Upstream SMTP server                                                      |
| `msmtp_relay_interface`    | Interface `msmtpd` listens on. Must be `127.0.0.1` or `::1`               |
| `msmtp_relay_port`         | Port `msmtpd` listens on. Must be unprivileged (1024 to 65535)            |

Set `msmtp_domain` and `msmtp_user` per host in `host_vars/`. `msmtp_password` comes from the broker, not
`host_vars`. The role's first task asserts the required variables and the relay constraints, before the next one
uninstalls the host's existing MTA.

## Installed files

| Path                                                 | Purpose                                                                                         |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `/etc/msmtprc`                                       | World-readable client config for `/usr/sbin/sendmail`; points at `msmtpd`, holds no credentials |
| `/etc/msmtprc-relay`                                 | `msmtpd`'s config, mode `0600`, holds the upstream credentials                                  |
| `/etc/systemd/system/msmtpd.service.d/override.conf` | Runs `msmtpd` as `User=msmtp`                                                                   |
| `/etc/apparmor.d/local/usr.bin.msmtp`                | Grants the msmtp profile read of `/etc/msmtprc-relay`                                           |
| `/etc/aliases`, `/etc/mailname`                      | Local delivery aliases and mail name                                                            |

## Notes

| Constraint                           | Detail                                                                                                                                                                                                                                                                            |
| ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Two config files                     | `/usr/sbin/sendmail` (from `msmtp-mta`) reads `/etc/msmtprc`, which must stay world-readable: cron drops to the crontab owner before invoking the MTA, and Ubuntu's `msmtp` is not setgid. It holds no credentials and points at `msmtpd`, which relays with `/etc/msmtprc-relay` |
| The relay is unauthenticated         | `msmtp_relay_interface` must stay on loopback. The port is unprivileged so the daemon needs no `CAP_NET_BIND_SERVICE`                                                                                                                                                             |
| `User=msmtp`, not `DynamicUser=true` | `msmtp` refuses a `-C` config containing secrets unless the calling euid owns it with no group or other permission bits, and a `DynamicUser` UID cannot own a file on disk. The drop-in restores the sandboxing `DynamicUser` implied                                             |
| AppArmor                             | The `msmtp` profile grants read of `/etc/msmtprc` but not `/etc/msmtprc-relay`. It is disabled by default; the role writes the local rule regardless, so enforcing the profile later does not reject every message                                                                |
| Restart order                        | `msmtpd` restarts when its packages, relay config or unit override change, before `/etc/msmtprc` is written to point clients at it. The handler is flushed at that point to keep that order. It holds no queue, so the restart loses no mail                                      |
| No queue                             | An unreachable upstream means the message is rejected, not retried. Anything that must survive an outage needs a queuing MTA                                                                                                                                                      |

## Operations

```bash
# Verify delivery end to end
echo test | mail -s test root
journalctl -u msmtpd -n 20
```
