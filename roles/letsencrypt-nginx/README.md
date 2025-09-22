# ansible-role-letsencrypt-nginx

An [Ansible](https://www.ansible.com/) role that provisions NGINX as a Docker container on Ubuntu with automated HTTPS certificate management via Let's Encrypt.

## Usage

```bash
make webservers

ansible-playbook --ask-become-pass webservers.yml --tags configuration
ansible-playbook --ask-become-pass webservers.yml --tags letsencrypt
ansible-playbook --ask-become-pass webservers.yml --tags nginx

ansible-playbook --ask-become-pass webservers.yml --tags nginx --limit webserverhostname1
```

### Private GitHub Repository Access

If your websites use private GitHub repositories, then configure Git credential helper on the target host:

1. Visit <https://github.com/settings/tokens>
2. Generate a new token (classic)
3. Select only the "repo" scope
4. Add the token to ~/.git-credentials

```bash
# These `git` operations are executed with `become: true`,
# so you should execute the following as root
git config --global credential.helper store
echo "https://<username>:<token>@github.com" > ~/.git-credentials
chmod 600 ~/.git-credentials
```

## Overview

This role automates the deployment and configuration of NGINX in a Docker container, with integrated Let's Encrypt certificate management. It supports multiple websites, authentication options, and proxy configurations.

## Features

- Automated HTTPS certificate provisioning and renewal
- Multiple website/domain support
- Basic authentication configuration
- Proxy setup with WebSocket support
- Self-signed certificate option
- Cloudflare DNS integration
- Network access control

## Requirements

- Ansible 2.9 or higher
- Ubuntu operating system
- Docker installed on target host

## Role Variables

See [default values](./defaults/main.yml).

### Required Variables

- `letsencryptnginx_account_email`: Email for Let's Encrypt registration
- `letsencryptnginx_acme_directory_url`: Let's Encrypt API endpoint

### Website Configuration

Each website in `letsencryptnginx_websites` supports:

```yaml
letsencryptnginx_websites:
  # Returns HTTP response code 404
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
    csr_commonName: *.example.com
    proxy_port: 8123
    proxy_https: False
    proxy_remove_authorization_header: False
    websocket_path: /api/websocket
```

### Systemd Integration

For special mount dependencies, create a service:

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

Then, enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable restart-nginx-after-nas.service
sudo systemctl restart restart-nginx-after-nas.service
```

## License

MIT License. See [LICENSE](../../LICENSE) for full details.
