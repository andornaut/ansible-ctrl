# ansible-role-letsencrypt_nginx

Installs NGINX as a Docker container with Let's Encrypt HTTPS certificates.

## Usage

```bash
make webservers
make webservers -- --tags nginx
```

## Tags

| Tag                                     | Description                                                                                                                                                                    |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| configuration                           | Regenerate NGINX configuration files                                                                                                                                           |
| cron                                    | Certificate renewal cron job                                                                                                                                                   |
| docker                                  | Manage the NGINX Docker container                                                                                                                                              |
| [letsencrypt](https://letsencrypt.org/) | Everything: certificates, configuration, container, and the renewal cron job                                                                                                   |
| nginx                                   | Everything: `webservers.yml` applies both `nginx` and `letsencrypt` at play level, so either selects every task. Only `configuration`, `cron`, `docker` and `www` narrow a run |
| www                                     | Set up web root directories and clone site repos                                                                                                                               |

## Variables

See [defaults/main.yml](./defaults/main.yml).

### Sites

Keys of each `letsencrypt_nginx_websites` entry. Only `domain` is required.

| Key                                           | Value                                                                                                                                                                                                                                                                            |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `domain`                                      | The site's name. Also names its web root `/var/www/<domain>` and its `.htpasswd`                                                                                                                                                                                                 |
| `csr_common_name`                             | Certificate common name, default `domain`. Sites sharing one share a certificate                                                                                                                                                                                                 |
| `use_selfsigned_certificate`                  | Serve the self-signed certificate and place no order                                                                                                                                                                                                                             |
| `cloudflare_api_token`, `cloudflare_api_zone` | Validate by DNS-01 in that zone instead of HTTP-01                                                                                                                                                                                                                               |
| `trusted_networks`                            | CIDRs allowed besides localhost. See [Access control](#access-control)                                                                                                                                                                                                           |
| `permit_untrusted_networks`                   | Open the site to every network. See [Access control](#access-control)                                                                                                                                                                                                            |
| `credentials`                                 | List of `{username, password}` for basic authentication on the whole site                                                                                                                                                                                                        |
| `aliases`                                     | List of `{file_basename, credentials}`: a named `.htpasswd` a location's `credentials` can point at                                                                                                                                                                              |
| `locations`                                   | List of `{src, dest}` served by `alias` with `autoindex`, plus optional `permit_untrusted_networks` and `credentials: {file_basename}`. `src` and `dest` must both end in `/` or neither, and `file_basename` must name an alias or a site with `credentials`; both are asserted |
| `proxy_port`                                  | Proxy `/` to `127.0.0.1:<port>`. Without it the site serves its web root                                                                                                                                                                                                         |
| `proxy_https`                                 | Proxy over HTTPS instead of HTTP                                                                                                                                                                                                                                                 |
| `proxy_remove_authorization_header`           | Drop the `Authorization` header before proxying                                                                                                                                                                                                                                  |
| `websocket_paths`                             | Paths proxied with the WebSocket upgrade headers, `/` included                                                                                                                                                                                                                   |
| `proxy_content`                               | Raw nginx directives appended to `location /`                                                                                                                                                                                                                                    |
| `content`                                     | Raw nginx configuration rendered above the site's server blocks                                                                                                                                                                                                                  |
| `hidden_patterns`                             | Regexes answered 404, added to `letsencrypt_nginx_hidden_patterns`                                                                                                                                                                                                               |
| `path`                                        | Subdirectory of the web root to serve, for a site with no `proxy_port`                                                                                                                                                                                                           |
| `default_path`                                | `try_files` fallback for a site with no `proxy_port`                                                                                                                                                                                                                             |
| `repo`, `version`                             | Git repository cloned into the web root, at `version` (default `HEAD`)                                                                                                                                                                                                           |

## Installed files

| Path                                              | Purpose                                                             |
| ------------------------------------------------- | ------------------------------------------------------------------- |
| `/usr/local/sbin/letsencrypt-nginx-renew`         | Renewal script, with `letsencrypt_nginx_install_renewal_cron: true` |
| `/etc/cron.d/ansible-role-letsencrypt_nginx`      | Root job that runs the renewal script                               |
| `/etc/logrotate.d/ansible-role-letsencrypt_nginx` | Weekly rotation of the renewal log, with the renewal cron           |

## Certificates

Per entry in `letsencrypt_nginx_websites`:

| Constraint                                                                                        | Detail                                                                                                                                                                                                                                                                                                                                                                                      |
| ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| One certificate per `csr_common_name`, or per `domain` where a site names none                    | Sites sharing a common name share one CSR and place one ACME order                                                                                                                                                                                                                                                                                                                          |
| A certificate covers its common name plus `<domain>` and `www.<domain>` for every site sharing it | Each site renders a server for its `domain` and a `www.` one that redirects to it. A name the common name already covers is not added: a wildcard covers one label below its base, so `example.com` under `*.example.com` gets its own name, as does `www.foo.example.com`                                                                                                                  |
| A site with `cloudflare_api_token` is validated by DNS-01, anything else by HTTP-01               | DNS-01 writes one TXT record per name into `cloudflare_api_zone`, and a wildcard needs it. HTTP-01 writes each name's token under the site's web root, the `www.` name's included: the port-80 server answers both from `/var/www/<domain>`                                                                                                                                                 |
| An HTTP-01 certificate's common name must be some site's `domain`                                 | Asserted before any order: its token is written to `/var/www/<common name>`, which only that site's port-80 server answers from. A wildcard needs DNS-01                                                                                                                                                                                                                                    |
| Challenge material is removed once the orders are completed                                       | The TXT records (by name and value, one per value: a wildcard and its base name share a record name) and HTTP-01 token files written for this run's orders, also when completing fails. That failure still fails the run                                                                                                                                                                    |
| `use_selfsigned_certificate: true` places no order                                                | The site serves the self-signed certificate, as does any site whose certificate has not been issued yet                                                                                                                                                                                                                                                                                     |
| `letsencrypt_nginx_account_email` is required                                                     | Asserted as the role's first task; every order names it                                                                                                                                                                                                                                                                                                                                     |
| `letsencrypt_nginx_acme_directory_url` defaults to Let's Encrypt's staging directory              | Set the production directory in `host_vars` for a trusted certificate. An existing certificate is reissued within `letsencrypt_nginx_remaining_days` of expiry, or whenever its names differ from its CSR's, which are compared on disk every run. For the run that switches directories, replace both `force` expressions in [tasks/letsencrypt.yml](./tasks/letsencrypt.yml) with `true`  |
| A new or changed server block is loaded before the challenges                                     | An HTTP-01 challenge is answered by the site's own server block                                                                                                                                                                                                                                                                                                                             |
| Every configuration is tested whole before it is installed                                        | Rendered into a staging directory and tested by `nginx -t` in a throwaway container of `letsencrypt_nginx_docker_image`, pulled first as the live container is, with the live container's volumes, `ssl/` and `basicauth/` included. A configuration nginx rejects fails the run before any live file changes. Under `--check` the test is skipped until the self-signed certificate exists |
| Every restart first tests the live configuration                                                  | In the same throwaway container, so the test runs whether or not the nginx container does. A failure leaves the container on the configuration it already loaded. `webservers.yml` sets `force_handlers`, so a later task failing does not drop a pending restart                                                                                                                           |

## Access control

Per site, on its main HTTPS server:

| Setting                                       | Effect                                                                  |
| --------------------------------------------- | ----------------------------------------------------------------------- |
| neither `trusted_networks` nor `credentials`  | Localhost only, unless `permit_untrusted_networks: true` opens the site |
| `trusted_networks`                            | Only localhost and those networks                                       |
| `credentials`                                 | HTTP basic authentication as well as the network restriction            |
| `permit_untrusted_networks: true` with either | Either one suffices: a trusted network, or valid credentials            |

Per entry in a site's `locations`:

| Setting                                             | Effect                                                                                     |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| none                                                | Inherits the site's access control                                                         |
| `permit_untrusted_networks: true`                   | Open to every network, without the site's network restriction or credentials               |
| `credentials`                                       | The location's credentials replace the site's; network rules and `satisfy` follow the site |
| `credentials` and `permit_untrusted_networks: true` | Either a trusted network or the location's credentials suffices                            |

## Certificate renewal

`letsencrypt_nginx_install_renewal_cron: true` installs the renewal script and its root cron job. Enable it on the
controller only.

| Constraint                    | Detail                                                                                                                                                                                                                                                                                                                                           |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| What a renewal runs           | `make webservers PREFLIGHT=none -- --tags letsencrypt` as root from `letsencrypt_nginx_renewal_cron_directory`, with `FARAMIR_OPERATOR` naming `letsencrypt_nginx_operator`. Root reads the store itself, so the run needs no escalation or become password, and it reissues any certificate within `letsencrypt_nginx_remaining_days` of expiry |
| Reachability probe            | Off, so every web server is attempted under ansible's own connect timeout. An unreachable one still fails the run                                                                                                                                                                                                                                |
| nginx restart                 | A completed challenge restarts nginx, whose configuration names the same certificate path before and after a renewal                                                                                                                                                                                                                             |
| Inputs in the operator's home | The checkout, `faramir.env`, the sops store, the age key and the broker's SSH key. If any is missing or unreadable, as while an encrypted home is unmounted, the script skips the run and prints the cause on stderr, which cron mails                                                                                                           |
| Log                           | The playbook's output goes to `letsencrypt_nginx_renewal_cron_log`. A failed run prints its location on stderr, which cron mails                                                                                                                                                                                                                 |

## Container ports

The `nginx` container runs with `network_mode: host`, binding directly to the host's network interfaces.

| Port | Protocol | Description                                       |
| ---- | -------- | ------------------------------------------------- |
| 80   | HTTP     | Redirect to HTTPS; ACME certificate validation    |
| 443  | HTTPS    | TLS-terminated reverse proxy with HTTP/2 and QUIC |

## Setup

### Web root on a mount

When the web root lives on a mount, restart NGINX after the mount comes up. Create
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
