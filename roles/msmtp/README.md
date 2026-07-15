# ansible-role-msmtp

Installs and configures [MSMTP](https://marlam.de/msmtp/) for email forwarding on Ubuntu.

## Usage

```bash
make msmtp
```

## Variables

See [defaults/main.yml](./defaults/main.yml).

| Variable | Purpose |
| --- | --- |
| `msmtp_domain` | Mail domain, used to build `msmtp_send_all_email_to`. Required |
| `msmtp_user` | Upstream SMTP username. Required |
| `msmtp_password_INSECURE` | Upstream SMTP password. Required, rendered into `/etc/msmtprc-relay` only |
| `msmtp_host`, `msmtp_port` | Upstream SMTP server |
| `msmtp_relay_interface` | Interface `msmtpd` listens on. Must be `127.0.0.1` or `::1` |
| `msmtp_relay_port` | Port `msmtpd` listens on. Must be unprivileged (1024 to 65535) |

Set the required vars per host in `host_vars/`. The role asserts them, and the relay constraints,
before its first task, which uninstalls the host's existing MTA.

## Design

- **Two config files.** Local mail is submitted via `/usr/sbin/sendmail` (from `msmtp-mta`), which
  reads world-readable `/etc/msmtprc`. That file must stay world-readable (cron drops to the crontab
  owner before invoking the MTA, and Ubuntu's `msmtp` is not setgid), so it holds no credentials: it
  points at `msmtpd` on the relay interface, which relays via `/etc/msmtprc-relay` (mode `0600`),
  where the credentials live.
- **The relay is unauthenticated**, so `msmtp_relay_interface` must stay on loopback. Its port is
  unprivileged so the daemon needs no `CAP_NET_BIND_SERVICE`.
- **A systemd drop-in sets `User=msmtp` instead of `DynamicUser=true`.** `msmtp` refuses a `-C` config
  containing secrets unless the file is owned by the calling euid with no group or other permission
  bits, and a `DynamicUser` UID can never own a file on disk. The drop-in also restores the sandboxing
  `DynamicUser` implied, so the daemon cannot rewrite the relay config it owns.
- **AppArmor.** `msmtp`'s profile grants read of `/etc/msmtprc` but not `/etc/msmtprc-relay`. It is
  disabled by default; the role writes the local rule regardless, so enforcing it later cannot bounce
  every message.
- **msmtpd is restarted every run**, before `/etc/msmtprc` is written to point clients at it. It holds
  no queue, so the restart is cheap and always safe.
- **msmtp does not queue.** An unreachable upstream means the message is rejected, not retried.
  Anything that must survive an outage needs a queuing MTA.

## Operations

```bash
# Verify delivery end to end
echo test | mail -s test root
journalctl -u msmtpd -n 20
```
