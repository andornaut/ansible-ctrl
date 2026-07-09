# ansible-role-msmtp

Installs and configures [MSMTP](https://marlam.de/msmtp/) for email forwarding on Ubuntu.

## Usage

```bash
make msmtp

# Verify delivery end to end
echo test | mail -s test root
journalctl -u msmtpd -n 20
```

## Design

Local mail is submitted through `/usr/sbin/sendmail` (provided by `msmtp-mta`), which
reads `/etc/msmtprc`. That file is world-readable, because cron drops privileges to the
crontab owner before invoking the MTA, and Ubuntu's `msmtp` package is not setgid.

To keep the upstream SMTP credentials off a world-readable file, `/etc/msmtprc` points at
`msmtpd` on `127.0.0.1:8025` and contains no credentials. `msmtpd` relays via
`/etc/msmtprc-relay`, which holds the credentials. The relay port is unprivileged so that
the daemon needs no `CAP_NET_BIND_SERVICE`; `msmtpd` authenticates nobody, so
`msmtp_relay_interface` must stay on loopback.

A systemd drop-in replaces the shipped unit's `DynamicUser=true` with `User=msmtp`, the
system user that `msmtp-mta` creates. This is required, not cosmetic: `msmtp` refuses a
config passed with `-C` that contains secrets unless the file is owned by the calling
euid and carries no group or other permission bits, and a `DynamicUser` UID can never own
a file on disk. `/etc/msmtprc-relay` is therefore `msmtp:msmtp` mode `0600`. The drop-in
also clears the shipped unit's `CAP_NET_BIND_SERVICE` grants, which the unprivileged port
makes dead weight.

`msmtp` ships an AppArmor profile that grants read access to `/etc/msmtprc` but not
`/etc/msmtprc-relay`. The profile is disabled by default (debconf `msmtp/apparmor`), but
the role writes the local rule at `/etc/apparmor.d/local/usr.bin.msmtp` regardless, so
enforcing the profile later cannot start bouncing every message. On hosts where the
profile is enforced, AppArmor is reloaded every run rather than on change, for the same
convergence reason as the msmtpd restart below.

msmtpd is restarted on every run, before `/etc/msmtprc` is written. It holds no queue, so
the restart is cheap, and gating it on a config change would let an interrupted run leave
the daemon on its packaged `ExecStart` while `/etc/msmtprc` already points at it, relaying
mail back into msmtpd.

Note that msmtp does not queue: if the upstream SMTP server is unreachable, the message is
rejected rather than retried. Anything that must survive an outage needs a queuing MTA.

## Variables

See [defaults/main.yml](./defaults/main.yml). `msmtp_domain`, `msmtp_user`, and
`msmtp_password_INSECURE` have no defaults: set them per host in `host_vars/` (gitignored). The password is
rendered into `/etc/msmtprc-relay` only. `msmtp_relay_interface` must stay on a loopback address, because
`msmtpd` accepts mail without authenticating the sender. The role asserts both before
touching anything, since its first real task uninstalls the host's existing MTA.
