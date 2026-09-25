# ansible-role-router

Installs health checks on the pfSense routers: a connectivity check that bounces the WAN interface, and a resolver
check that restarts unbound.

## Usage

```bash
make router
make router -- --tags dns-healthcheck
```

[router.yml](../../router.yml) applies this role to the `routers` group. Every feature is off by default; enable
the ones a host needs in its `host_vars`.

## Tags

| Tag               | Description                               |
| ----------------- | ----------------------------------------- |
| `pingtest`        | The connectivity check and its cron entry |
| `dns-healthcheck` | The resolver check and its cron entry     |

## Variables

See [defaults/main.yml](./defaults/main.yml), which comments the non-obvious ones.

| Variable                                                         | Purpose                                                                                    |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `router_install_pingtest`                                        | Install the connectivity check. Needs `router_pingtest_interface`                          |
| `router_pingtest_interface`                                      | Interface to bounce, as the kernel names it (`mvneta2`), not as the GUI labels it          |
| `router_pingtest_targets`                                        | Addresses to probe. Addresses, never names                                                 |
| `router_pingtest_minute`, `router_dns_healthcheck_minute`        | Cron minute field of each check's entry, `*/5` by default                                  |
| `router_pingtest_down_seconds`, `router_pingtest_settle_seconds` | Seconds the interface is held down, and the settle before the retry                        |
| `router_install_dns_healthcheck`                                 | Install the resolver check                                                                 |
| `router_dns_healthcheck_query`                                   | Name to query. Answered from unbound's local zone, so it needs no recursion                |
| `router_dns_healthcheck_confirm_seconds`                         | How long the resolver must stay silent before it is restarted                              |
| `router_dns_healthcheck_restart_timeout`                         | Bounds the restart call and the wait for an answer after it, each happening twice at worst |

## Installed files

| Path                                                                      | Purpose                                                                                      |
| ------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| [`/usr/local/bin/router-pingtest`](./files/router-pingtest)               | Bounces the interface on every run in which no target answers                                |
| [`/usr/local/bin/router-dns-healthcheck`](./files/router-dns-healthcheck) | Restarts the resolver when it stops answering, killing it if a restart cannot bind           |
| `/etc/cron.d/ansible-role-router`                                         | One entry per enabled check. Clearing a check's flag removes its entry and leaves its script |
| `/var/run/router-pingtest.lock`, `/var/run/router-dns-healthcheck.lock`   | Lock files; each mtime is that script's last run                                             |

## Notes

| Constraint                         | Detail                                                                                                                                                                                                                                                                                               |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Kernel address space sampler       | Not in this role. It runs on the Home Assistant host, reads a token from the ha-mcp container and writes an entity, so it is in [homeautomation](../homeautomation/README.md) as `homeautomation_install_router_kva_sample`                                                                          |
| Every task is `become: false`      | pfSense has no sudo, and ansible connects to the routers as root                                                                                                                                                                                                                                     |
| Cron entries in `/etc/cron.d/`     | pfSense regenerates `/etc/crontab` from `config.xml`, so an entry written there does not survive. The shipped file's own header names `/etc/cron.d/` as the alternative to the Cron package, and FreeBSD's cron reads it                                                                             |
| Restart through `pfSsh.php`        | `router-dns-healthcheck` runs `pfSsh.php playback svc restart unbound`, which calls `services_unbound_configure()` and rebuilds the chroot mounts. `/usr/local/etc/rc.d/unbound` alone leaves them stale                                                                                             |
| Short silences are ignored         | A silence shorter than `router_dns_healthcheck_confirm_seconds` is left alone. A DNSBL reload stops the resolver for about 30 seconds, and a restart during the reload makes two starts race for the port                                                                                            |
| One run at a time                  | A run can outlast the cron interval; the `lockf` keeps a second run out                                                                                                                                                                                                                              |
| Kill on the second attempt only    | A pfBlockerNG DNSBL reload stops unbound, waits a fixed 30 seconds, and starts it again. If the stop takes longer, the old process keeps `:53` and the new one fails with `address already in use`; the reload does not retry. A restart cannot displace the old process, so only the kill clears it |
| Every call bounded by `timeout(1)` | Both the resolver and pfSense block indefinitely when the resolver hangs. A query to a bound, silent port waits out drill's own retries, and pfSense's stop waits for a process that cannot handle the signal, so the kill would never run                                                           |
| Local-zone probe                   | An external name fails whenever the WAN is down, and restarting the resolver then fixes nothing and drops every cached answer                                                                                                                                                                        |
| Lock file mtime is the last run    | A healthy run logs nothing, and pfSense keeps no cron log and no `cron` syslog facility. `stat` the lock file to tell a passing check from one that stopped running. For `router-pingtest` the lock also stops one run downing the interface while another is probing it                             |
| `router-pingtest` takes addresses  | A name cannot distinguish a dead link from a resolver that stopped answering, and bouncing the WAN for the latter takes the link down for a minute with no effect                                                                                                                                    |
| `router-pingtest` does not reboot  | A reset that fails to restore the link twice in a row is a fault a reboot does not fix, and rebooting on a flapping upstream can keep the router in a boot loop for longer than the outage                                                                                                           |
| Logging through `logger`           | The system log is what the GUI shows and what `newsyslog` rotates; a private log file under `/root` is neither                                                                                                                                                                                       |
| Firmware upgrades remove the files | An upgrade removes the `/usr/local/bin/` scripts and the `/etc/cron.d/` entries. Neither is in `config.xml`, so neither is in a configuration backup. Re-run the play after an upgrade                                                                                                               |

## Setup

The DNSBL update start time is a pfBlockerNG setting (`pfb_hour` in `config.xml`), not managed here. Keep it off
`00:00`, where it shares the minute with the package's own `clearip` and `cleardnsbl` jobs and with
`/etc/rc.update_pkg_metadata`. Set it under **Firewall > pfBlockerNG > General > CRON Settings**.

## Operations

```bash
# Run the installed checks by hand
ssh root@<router> /usr/local/bin/router-dns-healthcheck localhost 90 45
ssh root@<router> /usr/local/bin/router-pingtest <interface> 10 60 1.1.1.1 8.8.8.8

# Last run of each check
ssh root@<router> stat /var/run/router-pingtest.lock /var/run/router-dns-healthcheck.lock
```
