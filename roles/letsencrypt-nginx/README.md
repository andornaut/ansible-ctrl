# ansible-role-letsencrypt-nginx

Provisions NGINX as a Docker container with Let's Encrypt HTTPS certificates.

## Usage

```bash
make webservers

ansible-playbook --ask-become-pass webservers.yml --tags configuration
ansible-playbook --ask-become-pass webservers.yml --tags letsencrypt
ansible-playbook --ask-become-pass webservers.yml --tags nginx

# Limit to specific host:
ansible-playbook --ask-become-pass webservers.yml --tags nginx --limit hostname
```

## Variables

See [defaults/main.yml](./defaults/main.yml).

### Required Variables

- `letsencryptnginx_account_email`: Email for Let's Encrypt registration
- `letsencryptnginx_acme_directory_url`: Let's Encrypt API endpoint

### Website Configuration

```yaml
letsencryptnginx_websites:
  # Returns HTTP 404
  - domain: subdomain.example.com
    use_selfsigned_certificate: true

  - domain: example.com
    repo: https://github.com/andornaut/example.com.git

  - domain: httpbasic.example.com
    http_basic_authentication:
      allowed_networks:
        - 192.168.0.0/16
      credentials:
        - username: hello
          password: world
    locations:
      - src: /nas
        dest: /media/nas

  - domain: proxy.example.com
    cloudflare_api_token: token
    cloudflare_api_zone: example.com
    csr_commonName: "*.example.com"
    proxy_port: 8123
    proxy_https: false
    proxy_remove_authorization_header: false
    websocket_path: /api/websocket
```

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
