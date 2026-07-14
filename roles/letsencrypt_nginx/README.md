# ansible-role-letsencrypt_nginx

Provisions NGINX as a Docker container with Let's Encrypt HTTPS certificates.

## Usage

```bash
make webservers
make webservers -- --tags nginx
```

## Tags

| Tag | Description |
| --- | --- |
| configuration | Regenerate NGINX configuration files |
| docker | Manage the NGINX Docker container |
| [letsencrypt](https://letsencrypt.org/) | Obtain and renew HTTPS certificates |
| nginx | Full NGINX setup (apt, www, basicauth, configuration) |
| www | Set up web root directories and clone site repos |

## Variables

See [defaults/main.yml](./defaults/main.yml).

## Container ports

The `nginx` container runs with `network_mode: host`, binding directly to the host's network interfaces.

| Port | Protocol | Description |
| --- | --- | --- |
| 80 | HTTP | Redirect to HTTPS; ACME certificate validation |
| 443 | HTTPS | TLS-terminated reverse proxy with HTTP/2 and QUIC |

## Notes

- Cloning private GitHub repos requires a git credential helper on the target host, configured as root because the
  git tasks use `become: true`. Generate a token at
  [github.com/settings/tokens](https://github.com/settings/tokens) with the `repo` scope only.

  ```bash
  git config --global credential.helper store
  echo "https://<username>:<token>@github.com" > ~/.git-credentials
  chmod 600 ~/.git-credentials
  ```

- When the web root lives on a mount, restart NGINX after the mount comes up. Create
  `/etc/systemd/system/restart-nginx-after-nas.service`:

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

  ```bash
  sudo systemctl daemon-reload
  sudo systemctl enable restart-nginx-after-nas.service
  ```
