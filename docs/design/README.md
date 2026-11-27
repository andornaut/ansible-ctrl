# Design

## Project-wide references

| Topic                                          | Authoritative reference                          |
| ---------------------------------------------- | ------------------------------------------------ |
| Fleet topology and inventory                   | [Inventory](../../README.md#inventory)           |
| Playbook preflight, credentials, and execution | [Usage](../../README.md#usage)                   |
| Secret handling                                | [Secrets](../../README.md#secrets)               |
| Local checks and CI                            | [Development](../../README.md#development)       |
| Task ownership and landing                     | [Coordination Kit setup](../coordination-kit.md) |

## Role references

| Area                       | Authoritative references                                                                                                                                                                                                                            |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Base configuration         | [Base](../../roles/base/README.md)                                                                                                                                                                                                                  |
| Desktops                   | [Desktop](../../roles/desktop/README.md), [bspwm](../../roles/bspwm/README.md), [niri](../../roles/niri/README.md)                                                                                                                                  |
| Development and containers | [Development tools](../../roles/dev/README.md), [Docker](../../roles/docker/README.md)                                                                                                                                                              |
| Security and networking    | [Faramir](../../roles/faramir/README.md), [Routers](../../roles/router/README.md), [Nginx and certificate renewal](../../roles/letsencrypt_nginx/README.md)                                                                                         |
| Storage and transfers      | [NAS](../../roles/nas/README.md), [Backups](../../roles/rsnapshot/README.md), [Torrents](../../roles/torrent/README.md)                                                                                                                             |
| Mail                       | [Mail forwarding](../../roles/msmtp/README.md)                                                                                                                                                                                                      |
| Home automation            | [Home Assistant](../../roles/homeautomation/README.md), [Hardware](../../roles/homeautomation/docs/hardware.md), [Troubleshooting](../../roles/homeautomation/docs/troubleshooting.md), [References](../../roles/homeautomation/docs/references.md) |
| Games and hobbies          | [Games](../../roles/games/README.md), [Game assets](../../roles/games/files/README.md), [Retroid sync](../../roles/games/files/retroid/README.md), [Hobbies](../../roles/hobbies/README.md)                                                         |
