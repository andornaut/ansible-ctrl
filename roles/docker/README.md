# ansible-role-docker

Installs Docker CE and Docker Compose on Ubuntu, and adds `docker_user` to the `docker` group.

Kubernetes utilities (helm, kubectl, minikube) and Docker Registry are optional and disabled by default.
Docker Registry binds host port 5000, which is also the port Frigate publishes by default, so enable it
per host rather than globally. Turning `docker_install_registry` back off stops the role installing and
starting the registry; it does not remove an existing one, because purging the package would delete
`/var/lib/docker-registry` and every image layer in it.

## Usage

```bash
make docker

# Kubernetes is gated on a flag as well as its tag, so the tag alone skips every task.
ansible-playbook --ask-become-pass docker.yml --tags kubernetes -e docker_install_kubernetes=true
```

The registry has no tag of its own: it is installed under the `docker` tag, gated on `docker_install_registry`.

## Variables

See [defaults/main.yml](./defaults/main.yml).
