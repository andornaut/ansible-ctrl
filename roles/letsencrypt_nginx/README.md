# ansible-role-letsencrypt_nginx

Provisions NGINX as a Docker container with Let's Encrypt HTTPS certificates.

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

## Certificates

Per entry in `letsencrypt_nginx_websites`:

| Rule                                                                                 | Detail                                                                                                                                                                                                                                                                                           |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| One certificate per `csr_common_name`, or per `domain` where a site names none       | Sites sharing a common name share one CSR and place one ACME order                                                                                                                                                                                                                               |
| A certificate covers its common name plus `www.<domain>` for every site sharing it   | Each site renders a `www.` server that redirects to the bare name. A wildcard common name already covers the `www.` name one label below it, so none is added                                                                                                                                    |
| A site with `cloudflare_api_token` is validated by DNS-01, anything else by HTTP-01  | DNS-01 writes one TXT record per name into `cloudflare_api_zone`, and a wildcard needs it. HTTP-01 writes each name's token under the site's web root, the `www.` name's included: the port-80 server answers both from `/var/www/<domain>`                                                      |
| An HTTP-01 certificate's common name must be some site's `domain`                    | Asserted before any order: its token is written to `/var/www/<common name>`, which only that site's port-80 server answers from. A wildcard needs DNS-01                                                                                                                                         |
| Challenge material is removed once the orders are completed                          | The TXT records (by name and value) and HTTP-01 token files written for this run's orders, also when completing fails. That failure still fails the run                                                                                                                                          |
| `use_selfsigned_certificate: true` places no order                                   | The site serves the self-signed certificate, as does any site whose certificate has not been issued yet                                                                                                                                                                                          |
| `letsencrypt_nginx_account_email` is required                                        | Asserted as the role's first task; every order names it                                                                                                                                                                                                                                          |
| `letsencrypt_nginx_acme_directory_url` defaults to Let's Encrypt's staging directory | Set the production directory in `host_vars` for a trusted certificate. An existing certificate is reissued only within `letsencrypt_nginx_remaining_days` of expiry, unless the `force: true` commented in [tasks/letsencrypt.yml](./tasks/letsencrypt.yml) is enabled for the run that switches |
| A new or changed server block is loaded before the challenges                        | An HTTP-01 challenge is answered by the site's own server block                                                                                                                                                                                                                                  |
| Every restart first runs `nginx -t` inside the running container                     | A configuration nginx rejects fails the run and leaves the container on the one it already loaded. `webservers.yml` sets `force_handlers`, so a later task failing does not drop a pending restart                                                                                               |

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

`letsencrypt_nginx_install_renewal_cron: true` installs `/usr/local/sbin/letsencrypt-nginx-renew` and a root job in
`/etc/cron.d/ansible-role-letsencrypt_nginx` that runs it. Enable it on the controller only: the script runs
`ansible-playbook webservers.yml --tags letsencrypt` from `letsencrypt_nginx_renewal_cron_directory` under
`sops exec-env`, which reissues any certificate within `letsencrypt_nginx_remaining_days` of expiry. A completed
challenge restarts nginx, whose configuration names the same certificate path before and after a renewal.

The checkout, `faramir.env`, the sops store, the age key and the broker's SSH key all sit in the operator's home.
If any is missing or unreadable, as it is while an encrypted home is unmounted, the script skips the run and
prints the cause on stderr, which cron mails. The playbook's own output goes to `letsencrypt_nginx_renewal_cron_log`.

## Container ports

The `nginx` container runs with `network_mode: host`, binding directly to the host's network interfaces.

| Port | Protocol | Description                                       |
| ---- | -------- | ------------------------------------------------- |
| 80   | HTTP     | Redirect to HTTPS; ACME certificate validation    |
| 443  | HTTPS    | TLS-terminated reverse proxy with HTTP/2 and QUIC |

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
