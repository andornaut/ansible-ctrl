# ansible-role-letsencrypt-nginx

An [Ansible](https://www.ansible.com/) role to provision an [NGINX HTTP server](https://www.nginx.com) as a
[Docker container](https://hub.docker.com/_/nginx) on Ubuntu and manage auto-renewal of HTTPS certificates using
[Let's Encrypt](https://letsencrypt.org/).

## Requirements

* [Ansible](https://www.ansible.com/) >= 2.9.0
* Docker installed on the target host
* Ubuntu operating system

## Features

* Automatic HTTPS certificate provisioning and renewal via Let's Encrypt
* Support for multiple websites/domains
* Basic authentication support
* Proxy configuration with WebSocket support
* Self-signed certificate option
* Cloudflare DNS integration
* Network access control

## Variables

### Required Variables

* `letsencryptnginx_account_email`: Email address for Let's Encrypt account registration
* `letsencryptnginx_acme_directory_url`: Let's Encrypt API endpoint URL
  * Testing: `https://acme-staging-v02.api.letsencrypt.org/directory`
  * Production: `https://acme-v02.api.letsencrypt.org/directory`

### Optional Variables

See [default values](./defaults/main.yml) for complete list of configuration options.

## Website Configuration Options

Each website in `letsencryptnginx_websites` supports the following options:

* `domain`: (Required) Domain name for the website
* `permit_untrusted_networks`: (Optional) Allow access from untrusted networks (default: false)
* `trusted_networks`: (Optional) List of CIDR ranges for trusted networks
* `use_selfsigned_certificate`: (Optional) Use self-signed certificate instead of Let's Encrypt
* `repo`: (Optional) Git repository containing website content
* `credentials`: (Optional) Basic authentication configuration
* `locations`: (Optional) Custom location configurations
* `cloudflare_api_token`: (Optional) Cloudflare API token for DNS verification
* `cloudflare_api_zone`: (Optional) Cloudflare zone name
* `proxy_port`: (Optional) Port number for proxy configuration
* `websocket_path`: (Optional) Path for WebSocket support

## Example Configuration

```yaml
letsencryptnginx_account_email: info@example.com
letsencryptnginx_acme_directory_url: https://acme-v02.api.letsencrypt.org/directory

letsencryptnginx_websites:
  # Basic public website
  - domain: public.example.com
    permit_untrusted_networks: true
    repo: https://github.com/andornaut/public.example.com.git

  # Self-signed certificate example
  - domain: public404selfsigned.example.com
    permit_untrusted_networks: true
    use_selfsigned_certificate: true

  # Basic authentication example
  - domain: basicauth.example.com
    credentials:
      - username: hello
        password: world
    locations:
      - src: /inherit-credentials
        dest: /var/www/inherit-credentials
      - src: /custom-credentials
        dest: /var/www/custom-credentials
        credentials:
          - username: foo
            password: bar
            file_basename: basicauth.example.com.nas
    permit_untrusted_networks: true
    trusted_networks:
      - 192.168.0.0/16

  # Proxy configuration with Cloudflare DNS
  - domain: privateproxy.example.com
    cloudflare_api_token: token
    cloudflare_api_zone: example.com
    csr_commonName: *.example.com
    permit_untrusted_networks: false
    proxy_port: 8123
    proxy_redirect_http: False
    proxy_remove_authorization_header: False
    websocket_path: /api/websocket
```

## Troubleshooting

### Restart Nginx after a folder is mounted

If you need Nginx to restart after a specific mount point is available:

1. Create a Systemd unit file:

   ```bash
   sudo systemctl edit --force --full restart-nginx-after-nas.service
   ```

2. Add the following configuration:

   ```ini
   [Unit]
   Description=Restart the Nginx Docker container after /media/nas has been mounted
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

3. Enable and start the service:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable restart-nginx-after-nas.service
   sudo systemctl restart restart-nginx-after-nas.service
   ```

## License

MIT

## Author

[andornaut](https://github.com/andornaut)
