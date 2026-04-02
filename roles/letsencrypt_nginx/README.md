# ansible-role-letsencrypt_nginx

Provisions NGINX as a Docker container with Let's Encrypt HTTPS certificates.

## Usage

```bash
make webservers

ansible-playbook --ask-become-pass webservers.yml --tags nginx
```

## Tags

| Tag | Description |
| --- | --- |
| configuration | Regenerate [NGINX](https://nginx.org/) configuration files |
| docker | Manage the NGINX [Docker](https://docs.docker.com/) container |
| [letsencrypt](https://letsencrypt.org/) | Obtain and renew HTTPS certificates |
| nginx | Full [NGINX](https://nginx.org/) setup (apt, www, basicauth, configuration) |
| www | Set up web root directories and clone site repos |

## Variables

See [defaults/main.yml](./defaults/main.yml).

## Container ports

The `nginx` container runs with `network_mode: host`, binding directly to the host's network interfaces.

| Port | Protocol | Description |
| --- | --- | --- |
| 80 | HTTP | Redirect to HTTPS; ACME certificate validation |
| 443 | HTTPS | TLS-terminated reverse proxy with HTTP/2 and QUIC |

## Private GitHub Repository Access

Configure Git credential helper on the target host:

```bash
# Run as root (these git operations use become: true)
git config --global credential.helper store
echo "https://<username>:<token>@github.com" > ~/.git-credentials
chmod 600 ~/.git-credentials
```

Generate token at [github.com/settings/tokens](https://github.com/settings/tokens) (select "repo" scope only)

## Systemd Integration

For mount dependencies, create `/etc/systemd/system/restart-nginx-after-nas.service`:

```ini
[Unit]
Description=Restart Nginx after mount
Requires=media-nas.mount
After=media-nas.mount

[Service]
Type=oneshot
ExecStartPre=sleep 30
ExecStart=docker restart nginx
RemainAfterExit=true

[Install]
WantedBy=media-nas.mount
```

Enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable restart-nginx-after-nas.service
```
