# ansible-role-letsencrypt-nginx

An [Ansible](https://www.ansible.com/) role to provision an [NGINX HTTP server](https://www.nginx.com) as a
[Docker container](https://hub.docker.com/_/nginx) on Ubuntu and manage auto-renewal of HTTPS certificates using
[Let's Encrypt](https://letsencrypt.org/).

## Requirements

* [Ansible](https://www.ansible.com/) >= 2.9.0

## Variables

See [default values](./defaults/main.yml).

## Example configuration

Be sure to set `letsencryptnginx_acme_directory_url` for production use.

```yaml
letsencryptnginx_account_email: info@example.com

# Production URL
letsencryptnginx_acme_directory_url: https://acme-v02.api.letsencrypt.org/directory

letsencryptnginx_websites:
  - domain: public.example.com
    permit_untrusted_networks: true
    repo: https://github.com/andornaut/public.example.com.git

  # Returns HTTP status code 404, because no destinations are configured
  - domain: public404selfsigned.example.com
    permit_untrusted_networks: true
    use_selfsigned_certificate: true

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

1. Create a Systemd unit file

   ```bash
   sudo systemctl edit --force --full restart-nginx-after-nas.service
   ```

1. Enter the following:

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

1. Run `sudo systemctl daemon-reload`
1. Run `sudo systemctl restart restart-nginx-after-nas.service`
