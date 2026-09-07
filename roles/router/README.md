# ansible-role-router

Health checks on the pfSense routers: a connectivity check that bounces the WAN interface, and a resolver
check that restarts unbound.

## Usage

```bash
make router

# Run the installed checks by hand
ssh root@<router> /usr/local/bin/router-dns-healthcheck localhost 90 45
ssh root@<router> /usr/local/bin/router-pingtest <interface> 10 60 1.1.1.1 8.8.8.8
```

[router.yml](../../router.yml) applies this role to the `routers` group.

The kernel address space sampler that reads `vm.kvm_free` off a router is **not** here. It runs on the Home
Assistant host, borrows a token from the ha-mcp container and writes an entity, so it lives in the
[homeautomation](../homeautomation/README.md) role as `homeautomation_install_router_kva_sample`.

Every feature is off by default. Enable the ones a host wants in its `host_vars`.

## Variables

See [defaults/main.yml](./defaults/main.yml), which comments the non-obvious ones.

| Variable                                                         | Description                                                                                |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `router_install_pingtest`                                        | Install the connectivity check. Needs `router_pingtest_interface`                          |
| `router_pingtest_interface`                                      | Interface to bounce, as the kernel names it (`mvneta2`), not as the GUI labels it          |
| `router_pingtest_targets`                                        | Addresses to probe. Addresses, never names                                                 |
| `router_pingtest_down_seconds`, `router_pingtest_settle_seconds` | Seconds the interface is held down, and the settle before the retry                        |
| `router_install_dns_healthcheck`                                 | Install the resolver check                                                                 |
| `router_dns_healthcheck_query`                                   | Name to query. Answered from unbound's local zone, so it needs no recursion                |
| `router_dns_healthcheck_confirm_seconds`                         | How long the resolver must stay silent before it is restarted                              |
| `router_dns_healthcheck_restart_timeout`                         | Bounds the restart call and the wait for an answer after it, each happening twice at worst |

## Tags

| Tag               | Applies                                   |
| ----------------- | ----------------------------------------- |
| `pingtest`        | The connectivity check and its cron entry |
| `dns-healthcheck` | The resolver check and its cron entry     |

## Scripts

Installed to `/usr/local/bin/` on the routers.

| Script                                                     | Purpose                                                                            |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| [`router-pingtest`](./files/router-pingtest)               | Bounces the interface when no target answers, twice, then gives up                 |
| [`router-dns-healthcheck`](./files/router-dns-healthcheck) | Restarts the resolver when it stops answering, killing it if a restart cannot bind |

## Behaviour

| Behaviour                                                                                                  | Constraint                                                                                                                                                                                                                                                                                                                                                             |
| ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Every task is `become: false`                                                                              | pfSense carries no sudo and ansible connects to the routers as root                                                                                                                                                                                                                                                                                                    |
| Cron entries go in `/etc/cron.d/ansible-role-router`                                                       | pfSense regenerates `/etc/crontab` from `config.xml`, so an entry written there does not survive. The shipped file's own header names `/etc/cron.d/` as the alternative to the Cron package, and FreeBSD's cron reads it                                                                                                                                               |
| `router-dns-healthcheck` restarts through `pfSsh.php playback svc restart unbound`                         | That routes to `services_unbound_configure()`, which rebuilds the chroot mounts. `/usr/local/etc/rc.d/unbound` alone leaves them stale                                                                                                                                                                                                                                 |
| A silence shorter than `router_dns_healthcheck_confirm_seconds` is left alone, and one run holds a `lockf` | A legitimate DNSBL reload stops the resolver for about 30 seconds, and restarting it mid-reload is how two starts race for the port, which is the failure this exists to clear rather than to cause. A run that escalates all the way can outlast the cron interval, so the lock rather than that arithmetic is what stops a later run from starting a second resolver |
| It kills the resolver only on the second attempt                                                           | A pfBlockerNG DNSBL reload stops unbound and starts it again, waiting a fixed 30 seconds for the stop. A teardown that overruns that leaves the old process holding `:53` while the replacement fails to bind with `address already in use`, and the reload path does not retry. A restart cannot displace it, so the kill is what clears it                           |
| Every call to the resolver and to pfSense is bounded by `timeout(1)`                                       | Both block indefinitely against the fault this exists for. A query to a port that is bound and silent waits out drill's own retries, and pfSense's stop signals the resolver and waits for a process that is not in a state to handle it, which leaves the kill unreachable                                                                                            |
| The probe queries a name unbound answers from its own local zone                                           | An external name fails whenever the WAN is down, and restarting the resolver over that fixes nothing while dropping every cached answer                                                                                                                                                                                                                                |
| `/var/run/router-dns-healthcheck.lock` is kept, and its mtime is the last run                              | Nothing else records that the check is alive: a healthy run logs nothing by design, and pfSense keeps no cron log and no `cron` syslog facility. `stat` the file to tell a check that is passing from one that stopped running                                                                                                                                         |
| `router-pingtest` takes addresses, not names                                                               | A name cannot tell a dead link from a resolver that stopped answering, and bouncing the WAN over the latter takes the link down for a minute to no effect                                                                                                                                                                                                              |
| `router-pingtest` does not reboot                                                                          | A reset that did not restore the link twice running is a fault a reboot does not address, and rebooting is how a router with a flapping upstream ends up in a boot loop that outlasts the outage                                                                                                                                                                       |
| Both scripts log through `logger`                                                                          | The system log is what the GUI shows and what `newsyslog` rotates; a private log file under `/root` is neither                                                                                                                                                                                                                                                         |
| A pfSense firmware upgrade removes `/usr/local/bin/` scripts and `/etc/cron.d/` entries                    | Neither is in `config.xml`, so neither is in a configuration backup. Re-run the play after an upgrade                                                                                                                                                                                                                                                                  |

## pfBlockerNG

The DNSBL update start time is a pfBlockerNG setting (`pfb_hour` in `config.xml`), not managed here. Keep it off
`00:00`, where it shares the minute with the package's own `clearip` and `cleardnsbl` jobs and with
`/etc/rc.update_pkg_metadata`. Set it under **Firewall > pfBlockerNG > General > CRON Settings**.
