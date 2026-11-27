# Fleet inventory

## Fleet terms

| Term       | Meaning                                                                                                               |
| ---------- | --------------------------------------------------------------------------------------------------------------------- |
| controller | The host Ansible runs from, and the only member of `faramir_controller`. The only host whose sudo prompts             |
| fleet      | Every other Ubuntu host, reached over SSH with NOPASSWD sudo                                                          |
| `faramir`  | Every host running the secret broker, the controller included                                                         |
| `routers`  | The pfSense routers. FreeBSD, so Ubuntu-only plays are `all:!routers` and [router.yml](../../router.yml) reaches them |

## Inventory

`hosts` and `host_vars/<host>.yml` are gitignored. Override role defaults (`roles/<role>/defaults/main.yml`) in
`host_vars/`. Every host names its address, port and login: root's cron and the broker do not read `~/.ssh/config`.

Find the local controller in the inventory by its `ansible_connection=local` entry.
The example uses documentation addresses.

```ini
controller ansible_host=192.0.2.10 ansible_port=22 ansible_user=operator ansible_connection=local ansible_local_become_success_timeout=120
example ansible_host=192.0.2.11 ansible_port=22 ansible_user=operator

[faramir]
controller

[faramir_controller]
controller

[desktop]
example

[all:vars]
primary_user=operator
```

Define no `localhost` host: some tasks delegate to the implicit one, and a defined one joins every
`hosts: all` play.
