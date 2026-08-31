# ansible-role-docker

Installs Docker CE and Docker Compose on Ubuntu, and adds `docker_user` to the `docker` group.

## Usage

```bash
make docker

# Kubernetes is gated on a flag as well as its tag, so the tag alone runs nothing
make docker ARGS='--tags kubernetes -e docker_install_kubernetes=true'
```

## Tags

| Tag        | Description                                                                       |
| ---------- | --------------------------------------------------------------------------------- |
| docker     | Docker CE, Docker Compose, and the Docker Registry when `docker_install_registry` |
| kubernetes | helm, kubectl, and minikube, gated on `docker_install_kubernetes`                 |

The registry has no tag of its own.

## Variables

See [defaults/main.yml](./defaults/main.yml).

## Notes

- Docker Registry binds host port 5000, which Frigate also publishes by default. Enable `docker_install_registry`
  per host, not globally.
- Clearing `docker_install_registry` stops installing and starting the registry but does not remove an existing
  one, whose purge would delete `/var/lib/docker-registry` and its image layers. Remove by hand.
