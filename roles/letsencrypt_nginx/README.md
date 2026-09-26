# ansible-role-letsencrypt_nginx

Installs NGINX as a Docker container with Let's Encrypt HTTPS certificates.

## Usage

```bash
make webservers
make webservers -- --tags nginx
```

## Tags

| Tag                                     | Description                                                                                   |
| --------------------------------------- | --------------------------------------------------------------------------------------------- |
| configuration                           | Regenerate NGINX configuration files                                                          |
| cron                                    | Certificate renewal cron job                                                                  |
| docker                                  | Manage the NGINX Docker container                                                             |
| [letsencrypt](https://letsencrypt.org/) | Everything: certificates, configuration, container, and the renewal cron job                  |
| nginx                                   | Everything, like `letsencrypt`. Only `configuration`, `cron`, `docker` and `www` narrow a run |
| www                                     | Set up web root directories and clone site repos                                              |

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

## Certificates

| Constraint                            | Detail                                                                                                                                                                      |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| One certificate per `csr_common_name` | Or per `domain` where a site names none. It covers the common name plus `<domain>` and `www.<domain>` of every site sharing it                                              |
| Validation                            | DNS-01 in `cloudflare_api_zone` for a site with `cloudflare_api_token`, HTTP-01 otherwise. A wildcard needs DNS-01, and an HTTP-01 common name must be some site's `domain` |
| `letsencrypt_nginx_account_email`     | Required                                                                                                                                                                    |
| Staging by default                    | `letsencrypt_nginx_acme_directory_url` defaults to Let's Encrypt's staging directory. Set the production one in `host_vars`; staging certificates are then reissued         |
| Reissue                               | Within `letsencrypt_nginx_remaining_days` of expiry, or when a certificate's names change                                                                                   |
| Before issue                          | A site serves the self-signed certificate until its own is issued, and always with `use_selfsigned_certificate: true`                                                       |
| Configuration is tested               | A configuration `nginx -t` rejects fails the run before any live file changes                                                                                               |

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

`letsencrypt_nginx_install_renewal_cron: true` installs `/usr/local/sbin/letsencrypt-nginx-renew` and a root cron job
that runs `make webservers -- --tags letsencrypt`. Enable it on the controller only.

| Constraint                    | Detail                                                                                                                                                              |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| No reachability probe         | An unreachable web server fails the run                                                                                                                             |
| Inputs in the operator's home | The checkout, `faramir.env`, the sops store and the keys. While any is unreadable, as with an unmounted encrypted home, the run is skipped and cron mails the cause |
| Log                           | `letsencrypt_nginx_renewal_cron_log`. A failed run mails its location                                                                                               |

## Container ports

The `nginx` container uses the host's network.

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
