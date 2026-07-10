# ansible-role-docker

Installs Docker CE and Docker Compose on Ubuntu, and adds `docker_user` to the `docker` group.

## Usage

```bash
make docker

# Kubernetes is gated on a flag as well as its tag, so the tag alone runs nothing.
ansible-playbook --ask-become-pass docker.yml --tags kubernetes -e docker_install_kubernetes=true
```

## Tags

| Tag | Description |
| --- | --- |
| docker | Docker CE, Docker Compose, and the Docker Registry when `docker_install_registry` |
| kubernetes | helm, kubectl, and minikube, gated on `docker_install_kubernetes` |

The registry has no tag of its own.

## Variables

See [defaults/main.yml](./defaults/main.yml).

| Variable | Default | Purpose |
| --- | --- | --- |
| `docker_user` | remote user | Account added to the `docker` group |
| `docker_install_kubernetes` | `false` | Install helm, kubectl, and minikube |
| `docker_install_registry` | `false` | Install and start Docker Registry |

## Notes

- Docker Registry binds host port 5000, which Frigate also publishes by default. Enable
  `docker_install_registry` per host rather than globally.
- Setting `docker_install_registry` back to `false` stops the role installing and starting the registry, but does
  not remove an existing one: purging the package would delete `/var/lib/docker-registry` and every image layer
  in it.
