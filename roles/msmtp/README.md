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

Set `msmtp_domain` and `msmtp_user` per host in `host_vars/`. `msmtp_password` comes from the broker.

## Installed files

| Path                                                 | Purpose                                                                          |
| ---------------------------------------------------- | -------------------------------------------------------------------------------- |
| `/etc/msmtprc`                                       | Client config for `/usr/sbin/sendmail`; points at `msmtpd`, holds no credentials |
| `/etc/msmtprc-relay`                                 | `msmtpd`'s config, mode `0600`, holds the upstream credentials                   |
| `/etc/systemd/system/msmtpd.service.d/override.conf` | Runs `msmtpd` as `User=msmtp`                                                    |
| `/etc/apparmor.d/local/usr.bin.msmtp`                | Grants the msmtp profile read of `/etc/msmtprc-relay`                            |
| `/etc/aliases`, `/etc/mailname`                      | Local delivery aliases and mail name                                             |

## Notes

| Constraint                   | Detail                                                                                                                       |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Replaces the MTA             | The role uninstalls the host's existing MTA                                                                                  |
| The relay is unauthenticated | `msmtp_relay_interface` must stay on loopback                                                                                |
| No queue                     | An unreachable upstream means the message is rejected, not retried. Anything that must survive an outage needs a queuing MTA |

## Operations

```bash
# Verify delivery end to end
echo test | mail -s test root
journalctl -u msmtpd -n 20
```
