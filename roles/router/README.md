# ansible-role-router

Health checks on the pfSense routers, and the router-facing tooling that runs on the controller.

- **Routers:** a connectivity check that bounces the WAN interface, and a resolver check that restarts unbound.
- **Controller:** the kernel address space sampler that pushes `vm.kvm_free` to Home Assistant.

## Usage

```bash
make router

# One half at a time
make router -- --limit routers
make router -- --limit faramir_controller

# Run the installed checks by hand
ssh root@<router> /usr/local/bin/router-dns-healthcheck localhost 90 45
ssh root@<router> /usr/local/bin/router-pingtest <interface> 10 60 1.1.1.1 8.8.8.8
/usr/local/bin/router-kva-sample <router> <entity_id>
```

[router.yml](../../router.yml) has two plays. The first applies this role to the `routers` group; the second
imports [tasks/kva-sample.yml](./tasks/kva-sample.yml) against `faramir_controller` with `tasks_from`.

A second play rather than `delegate_to: localhost`, because the sampler's subject is the controller: it installs
a script and a cron entry there, owned by the controller's account and reading a token from a container on it. A
delegated task resolves plain variables from the play host, so delegation would put the controller's settings in
a router's `host_vars`.

Every feature is off by default. Enable the ones a host wants in its `host_vars`.

## Variables

See [defaults/main.yml](./defaults/main.yml), which comments the non-obvious ones.

| Variable                                                         | Description                                                                                      |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `router_install_pingtest`                                        | Install the connectivity check. Needs `router_pingtest_interface`                                |
| `router_pingtest_interface`                                      | Interface to bounce, as the kernel names it (`mvneta2`), not as the GUI labels it                |
| `router_pingtest_targets`                                        | Addresses to probe. Addresses, never names                                                       |
| `router_pingtest_down_seconds`, `router_pingtest_settle_seconds` | Seconds the interface is held down, and the settle before the retry                              |
| `router_install_dns_healthcheck`                                 | Install the resolver check                                                                       |
| `router_dns_healthcheck_query`                                   | Name to query. Answered from unbound's local zone, so it needs no recursion                      |
| `router_dns_healthcheck_confirm_seconds`                         | How long the resolver must stay silent before it is restarted                                    |
| `router_dns_healthcheck_restart_timeout`                         | Bounds the restart call and the wait for an answer after it, each happening twice at worst       |
| `router_install_kva_sample`                                      | Install the kernel address space sampler on the controller                                       |
| `router_kva_sample_host`                                         | Router the sampler reads `vm.kvm_free` from over ssh. Required                                   |
| `router_kva_sample_entity_id`                                    | Home Assistant entity the sampler writes                                                         |
| `router_kva_sample_container`                                    | Container the sampler borrows a Home Assistant token from, so none is written to disk            |
| `router_kva_sample_user`                                         | Controller account that owns the cron entry. Not root: the key and the docker group are a user's |

## Tags

| Tag               | Applies                                   |
| ----------------- | ----------------------------------------- |
| `pingtest`        | The connectivity check and its cron entry |
| `dns-healthcheck` | The resolver check and its cron entry     |

The controller half has no tag of its own: it is a whole play, selected with `--limit faramir_controller`.

## Scripts

Installed to `/usr/local/bin/`.

| Script                                                     | Host       | Purpose                                                                            |
| ---------------------------------------------------------- | ---------- | ---------------------------------------------------------------------------------- |
| [`router-pingtest`](./files/router-pingtest)               | router     | Bounces the interface when no target answers, twice, then gives up                 |
| [`router-dns-healthcheck`](./files/router-dns-healthcheck) | router     | Restarts the resolver when it stops answering, killing it if a restart cannot bind |
| [`router-kva-sample`](./files/router-kva-sample)           | controller | Reads `vm.kvm_free` off a router and pushes it to Home Assistant                   |

## Behaviour

| Behaviour                                                                                                  | Constraint                                                                                                                                                                                                                                                                                                                                   |
| ---------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Every task is `become: false`                                                                              | pfSense carries no sudo and ansible connects to the routers as root. The controller half is `become: true`, being an ordinary Ubuntu host                                                                                                                                                                                                    |
| Cron entries go in `/etc/cron.d/ansible-role-router` on both halves                                        | pfSense regenerates `/etc/crontab` from `config.xml`, so an entry written there does not survive. The shipped file's own header names `/etc/cron.d/` as the alternative to the Cron package, and FreeBSD's cron reads it                                                                                                                     |
| `router-dns-healthcheck` restarts through `pfSsh.php playback svc restart unbound`                         | That routes to `services_unbound_configure()`, which rebuilds the chroot mounts. `/usr/local/etc/rc.d/unbound` alone leaves them stale                                                                                                                                                                                                       |
| A silence shorter than `router_dns_healthcheck_confirm_seconds` is left alone, and one run holds a `lockf` | A legitimate DNSBL reload stops the resolver for about 30 seconds, and restarting it mid-reload is how two starts race for the port, which is the failure this exists to clear rather than to cause. The whole run is bounded by that window plus two restart timeouts, which stays under the cron interval so two runs never overlap        |
| It kills the resolver only on the second attempt                                                           | A pfBlockerNG DNSBL reload stops unbound and starts it again, waiting a fixed 30 seconds for the stop. A teardown that overruns that leaves the old process holding `:53` while the replacement fails to bind with `address already in use`, and the reload path does not retry. A restart cannot displace it, so the kill is what clears it |
| Every call to the resolver and to pfSense is bounded by `timeout(1)`                                       | Both block indefinitely against the fault this exists for. A query to a port that is bound and silent waits out drill's own retries, and pfSense's stop signals the resolver and waits for a process that is not in a state to handle it, which leaves the kill unreachable                                                                  |
| The probe queries a name unbound answers from its own local zone                                           | An external name fails whenever the WAN is down, and restarting the resolver over that fixes nothing while dropping every cached answer                                                                                                                                                                                                      |
| `router-pingtest` takes addresses, not names                                                               | A name cannot tell a dead link from a resolver that stopped answering, and bouncing the WAN over the latter takes the link down for a minute to no effect                                                                                                                                                                                    |
| `router-pingtest` does not reboot                                                                          | A reset that did not restore the link twice running is a fault a reboot does not address, and rebooting is how a router with a flapping upstream ends up in a boot loop that outlasts the outage                                                                                                                                             |
| Both router scripts log through `logger`                                                                   | The system log is what the GUI shows and what `newsyslog` rotates; a private log file under `/root` is neither                                                                                                                                                                                                                               |
| The sampler runs as `router_kva_sample_user`, not root                                                     | The key that reaches the router and the docker group that reads the token are that account's, and root's ssh configuration on the controller is hand-maintained rather than provisioned here                                                                                                                                                 |
| A pfSense firmware upgrade removes `/usr/local/bin/` scripts and `/etc/cron.d/` entries                    | Neither is in `config.xml`, so neither is in a configuration backup. Re-run the play after an upgrade                                                                                                                                                                                                                                        |

## pfBlockerNG

The DNSBL update start time is a pfBlockerNG setting (`pfb_hour` in `config.xml`), not managed here. Keep it off
`00:00`, where it shares the minute with the package's own `clearip` and `cleardnsbl` jobs and with
`/etc/rc.update_pkg_metadata`. Set it under **Firewall > pfBlockerNG > General > CRON Settings**.
