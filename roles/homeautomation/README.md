# ansible-role-homeautomation

Installs [Home Assistant](https://www.home-assistant.io/) and the services listed under [Tags](#tags) as Docker
containers.

[![homeassistant](https://raw.githubusercontent.com/andornaut/homeassistant-ibm1970-theme/main/screenshots/dark-colors-small.png)](https://github.com/andornaut/homeassistant-ibm1970-theme/blob/main/screenshots/dark-colors.png)

## Usage

```bash
make homeautomation
make homeautomation -- --tags frigate
```

## Tags

Every optional service is also gated on its `homeautomation_install_*` flag, so the tag alone installs nothing. See
[Removing a component](#removing-a-component).

| Tag                                                               | Description                                                                                                                                                                              |
| ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [adb_auto_enable](https://github.com/mouldybread/adb-auto-enable) | Installs the newest adb-auto-enable release on each Android TV. See [Android TV adb](docs/troubleshooting.md#android-tv-adb)                                                             |
| [avahi](https://avahi.org/)                                       | mDNS discovery service                                                                                                                                                                   |
| bluetooth                                                         | BLE access for the Home Assistant container. No flag; always applied                                                                                                                     |
| customizations                                                    | HA custom components, themes, www assets, and `frontend.yaml`                                                                                                                            |
| docker                                                            | All Docker container tasks                                                                                                                                                               |
| [esphome](https://esphome.io/)                                    | ESP device firmware and dashboard                                                                                                                                                        |
| [frigate](https://github.com/blakeblackshear/frigate)             | Video surveillance with AI detection                                                                                                                                                     |
| [hamcp](https://github.com/homeassistant-ai/ha-mcp)               | Home Assistant MCP server                                                                                                                                                                |
| homeassistant                                                     | [Home Assistant](https://www.home-assistant.io/) core with [Mosquitto](https://mosquitto.org/) and [Govee2MQTT](https://github.com/wez/govee2mqtt)                                       |
| llm                                                               | [llama.cpp](https://github.com/ggml-org/llama.cpp) and [Open WebUI](https://github.com/open-webui/open-webui)                                                                            |
| matter                                                            | [Matter.js](https://github.com/matter-js/matter.js) or [Python Matter Server](https://github.com/matter-js/python-matter-server), and [OTBR](https://openthread.io/guides/border-router) |
| [memryx](https://memryx.com/)                                     | MemryX MX3 AI accelerator drivers                                                                                                                                                        |
| [mosquitto](https://mosquitto.org/)                               | The MQTT broker's config. No flag; also applied by `homeassistant`                                                                                                                       |
| otbr                                                              | Host sysctls the border router needs, gated on either Matter flag. The OTBR container is under `matter`                                                                                  |
| router-kva-sample                                                 | The [router kernel address space sampler](#router-kernel-address-space-sampler), gated on `homeautomation_install_router_kva_sample`                                                     |
| teardown                                                          | Remove the containers and host files of components this host does not install                                                                                                            |
| voice                                                             | [Piper](https://github.com/rhasspy/piper) TTS and [Whisper](https://github.com/OHF-Voice/wyoming-faster-whisper) STT                                                                     |

## Variables

See [defaults/main.yml](./defaults/main.yml). The ones that need a decision per host:

| Variable                                                   | Purpose                                                                                                                                                                                          |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `homeautomation_install_*`                                 | One flag per optional service                                                                                                                                                                    |
| `homeautomation_*_uid`                                     | Fixed uid of each container's service account, distinct across the role                                                                                                                          |
| `homeautomation_*_port`                                    | Host port: the published port of a bridge container, or the listen port of a host-network one. See [Container ports](#container-ports)                                                           |
| `homeautomation_*_bind*`                                   | Listen addresses of the loopback-bound listeners. See [Container hardening](#container-hardening)                                                                                                |
| `homeautomation_hamcp_instances`                           | One entry per [ha-mcp](#ha-mcp) instance                                                                                                                                                         |
| `homeautomation_otbr_device`, `_backbone_if`               | With Matter: the Thread radio, and the LAN interface (default: the default route's). Asserted                                                                                                    |
| `homeautomation_homeassistant_devices`                     | Devices passed to the Home Assistant container. See [Notes](#notes)                                                                                                                              |
| `homeautomation_adb_auto_enable_hosts`                     | The Android TVs that receive adb-auto-enable                                                                                                                                                     |
| `homeautomation_llamacpp_models`, `_env`, `_model_presets` | See [llama.cpp models and context](#llamacpp-models-and-context)                                                                                                                                 |
| `homeautomation_homeassistant_extra_module_urls`           | Frontend modules to load from `www/`. See [Notes](#notes)                                                                                                                                        |
| `homeautomation_router_kva_sample_*`                       | See [Router kernel address space sampler](#router-kernel-address-space-sampler)                                                                                                                  |
| `homeautomation_esphome_username`, `_password`             | The ESPHome dashboard login. Asserted set unless `homeautomation_esphome_allow_unauthenticated`                                                                                                  |
| `homeautomation_homeassistant_patch_aioruckus_head`        | Where the Ruckus integration is used: patches aioruckus to send GET instead of HEAD, which aiohttp 3.14+ rejects. WORKAROUND for [aioruckus#14](https://github.com/ms264556/aioruckus/issues/14) |

## Installed files

| Path                                                                                                  | Purpose                                                                                                         |
| ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `/usr/local/bin/docker_etc_hosts`, `/etc/systemd/system/docker-etc-hosts.service`                     | [docker_etc_hosts](https://github.com/andornaut/docker_etc_hosts). See [Networking](#networking)                |
| `/etc/apparmor.d/docker-ble-policy`                                                                   | The AppArmor profile the Home Assistant container runs under, for BLE                                           |
| `/etc/sysctl.d/60-esphome-ping.conf`                                                                  | With ESPHome: `ping_group_range` scoped to the ESPHome gid, for the dashboard's ping                            |
| `/etc/sysctl.conf`                                                                                    | With either Matter flag: the OTBR forwarding and router-advertisement sysctls                                   |
| `/etc/nftables.d/homeautomation-otbr.nft`, `/etc/systemd/system/homeautomation-otbr-firewall.service` | With either Matter flag: the [OTBR REST API firewall](#otbr-rest-api-firewall). Removed with both flags cleared |
| `/etc/apt/keyrings/memryx.asc`, `/etc/apt/sources.list.d/memryx.list`                                 | With MemryX: its apt repository                                                                                 |
| `/usr/local/bin/router-kva-sample`                                                                    | [Router kernel address space sampler](#router-kernel-address-space-sampler)                                     |
| `/etc/cron.d/ansible-role-homeautomation`                                                             | Its hourly cron entry                                                                                           |

## Networking

| Mode                                      | Containers                                                  | Detail                                                                                                                                                                    |
| ----------------------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| host                                      | homeassistant, govee2mqtt, esphome, otbr, the Matter server | Need mDNS or LAN broadcast discovery                                                                                                                                      |
| `homeautomation_default` (`br-ha`) bridge | everything else but ha-mcp                                  | Containers reach each other by container name via Docker's DNS. One that must reach a host-networked service uses `extra_hosts: ["host.docker.internal:host-gateway"]`    |
| `homeautomation-<name>_default` bridge    | the ha-mcp instances                                        | One per instance, created by its compose project, so no other container reaches a server that authenticates nobody. `<name>.internal` still resolves from the Docker host |

| Constraint        | Detail                                                                                                                                                                                                                                                                                     |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `.internal` names | Every container resolves from the Docker host as `{container_name}.internal`, via [docker_etc_hosts](https://github.com/andornaut/docker_etc_hosts). A bridge container's name resolves to its bridge IP, so use the internal port: openwebui listens on 8080 and publishes host port 3000 |

### Container ports

Internal ports. The `homeautomation_*_port` variables set the published host side of a bridge container's
mapping, not the internal port listed here.

| Container          | Network | Port  | Protocol | Description                                              |
| ------------------ | ------- | ----- | -------- | -------------------------------------------------------- |
| homeassistant      | host    | 8123  | HTTP     | Web UI and API                                           |
| esphome            | host    | 6052  | HTTP     | Dashboard                                                |
| govee2mqtt         | host    | 8056  | HTTP     | Web UI and API; UDP LAN discovery                        |
| otbr               | host    | 8080  | HTTP     | Thread Border Router web UI, loopback only               |
| otbr               | host    | 8081  | REST     | Thread Border Router REST API, loopback only by nftables |
| matterjs           | host    | 5580  | HTTP/WS  | Web UI and WebSocket API, loopback only                  |
| pythonmatterserver | host    | 5580  | HTTP/WS  | As matterjs (legacy)                                     |
| mosquitto          | bridge  | 1883  | MQTT     | MQTT broker                                              |
| frigate            | bridge  | 5000  | HTTP     | Web UI (unauthenticated), loopback only                  |
| frigate            | bridge  | 8971  | HTTPS    | Web UI (authenticated), loopback only                    |
| frigate            | bridge  | 8554  | RTSP     | RTSP restream, loopback only                             |
| frigate            | bridge  | 8555  | WebRTC   | WebRTC streams                                           |
| llamacpp           | bridge  | 8080  | HTTP     | Web UI and OpenAI-compatible API                         |
| openwebui          | bridge  | 8080  | HTTP     | Web UI, published on host loopback port 3000             |
| hamcp              | bridge  | 8086  | HTTP     | MCP server                                               |
| piper              | bridge  | 10200 | Wyoming  | Text-to-speech, also on host loopback                    |
| whisper            | bridge  | 10300 | Wyoming  | Speech-to-text, also on host loopback                    |

## Container hardening

Per-service values are in [defaults/main.yml](./defaults/main.yml). Each non-root container runs as its own host
account with a fixed uid, `cap_drop: ALL` and `no-new-privileges`.

| Constraint                                   | Detail                                                                                                                                                                                                                                             |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Loopback listeners                           | The MQTT broker, Wyoming, the Matter WebSocket API, the OTBR web UI, Frigate's RTSP restream and Frigate's unauthenticated UI authenticate nobody, so all bind to loopback. Frigate's authenticated UI and OpenWebUI are reached through the proxy |
| Unauthenticated listeners on every interface | govee2mqtt's HTTP API, whose image hard-codes the listen address. OTBR's REST API does too, and is firewalled to loopback (see [OTBR REST API firewall](#otbr-rest-api-firewall))                                                                  |
| Frigate RTSP from the LAN                    | Home Assistant reaches the restream over the bridge. Set `homeautomation_frigate_bind_rtsp: "0.0.0.0"` only for an RTSP client off the host                                                                                                        |

## llama.cpp models and context

Each model runs in its own `llama-server` child, which defaults to a 4096-token context unless set here:

| Variable                                | Scope       | Holds                                                                                                                                        |
| --------------------------------------- | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `homeautomation_llamacpp_env`           | every model | `LLAMA_ARG_CTX_SIZE` (per-request context), `LLAMA_ARG_N_PARALLEL: "1"` (one slot) and `LLAMA_ARG_MODELS_MAX: "1"` (models resident at once) |
| `homeautomation_llamacpp_model_presets` | one model   | Any `llama-server` long option. A section name must match the model id, which is the file name                                               |

| Constraint             | Detail                                                                                                                                                               |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Context ceiling        | `LLAMA_ARG_CTX_SIZE` must not exceed the smallest model's native training context. A model that cannot fit it in VRAM sets a lower `c` in its own preset             |
| KV cache sizing        | Only full-attention layers hold KV cache, so a hybrid model needs far less per token than its parameter count suggests. Size a model as weights + KV against the GPU |
| Cache quantization     | Quantize the cache (`cache-type-k`, `cache-type-v`, which need `flash-attn = on`) before reducing context. Keep `cache-type-k` the higher precision of the two       |
| `LLAMA_ARG_MODELS_MAX` | `1` because one 27B quant plus its cache fills a 16GB GPU. At 1 a request naming a different model costs an unload and reload                                        |
| Preset keys            | Some command-line options are rejected in a preset, `reasoning-effort` and `n-parallel` among them. A rejected key stops the container from starting                 |

### Conversation agent

Assist talks to llama.cpp through the built-in
[llama.cpp integration](https://www.home-assistant.io/integrations/llama_cpp) (Home Assistant 2026.8 and later):
Settings > Devices & services, URL `http://llamacpp.internal:8080/v1`, the trailing `/v1` required. Every model in
the models directory is listed, so several agents can run different models. The role deletes no model: one dropped
from `homeautomation_llamacpp_models` stays listed until its file is removed by hand. An agent sees only entities
exposed to Assist, and does not fire [sentence triggers](https://www.home-assistant.io/docs/automation/trigger/#sentence-trigger).

## Matter and Thread

| Constraint                                 | Detail                                                                                                                    |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| Exactly one Matter server                  | `homeautomation_install_matterjs` or the superseded `homeautomation_install_pythonmatterserver`, asserted not both        |
| The Matter server must use host networking | mDNS does not cross the Docker bridge: a bridged Matter server resolves no node and every Matter device shows unavailable |
| Avahi cannot run alongside Matter/Thread   | A second mDNS responder conflicts, so `avahi-daemon` is masked while either Matter flag is on                             |

## ha-mcp

[ha-mcp](https://github.com/homeassistant-ai/ha-mcp) exposes Home Assistant to AI assistants over the
[Model Context Protocol](https://modelcontextprotocol.io/docs/2026-07-28/getting-started/intro). Clients connect to
`http://<name>.internal:8086/mcp`. See [Setup](#setup).

| Constraint                                                                           | Detail                                                                                                             |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| One instance per Home Assistant an assistant drives, all on the assistant's own host | A remote instance is reached by pointing its `url` at that Home Assistant. No MCP port is published                |
| Each entry needs its own `name` and `uid`                                            | The name is the container name and the service account; the uid must be above 10000 and distinct across this role  |
| Any local account on the host can reach it                                           | ha-mcp authenticates nobody, so any process on the host can act on Home Assistant with that instance's admin token |

## Router kernel address space sampler

`homeautomation_install_router_kva_sample` installs an hourly cron job that reads `vm.kvm_free` from a pfSense
router over ssh and writes it to `homeautomation_router_kva_sample_entity_id`, using the token of the
`homeautomation_router_kva_sample_container` ha-mcp container.

| Constraint                                      | Detail                                                                                                                                     |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Runs as `homeautomation_router_kva_sample_user` | That account needs the key that reaches the router and membership in the docker group                                                      |
| 32-bit routers only                             | The kernel map only shrinks over an uptime. At zero, rule changes silently stop loading until a reboot. An amd64 router never reaches zero |
| Unchanged readings                              | A steady figure updates only `last_reported`, so a working sampler looks stale in the UI                                                   |
| Threshold                                       | Set in a Home Assistant automation, not here                                                                                               |

## Removing a component

Clearing a `homeautomation_install_*` flag removes the component on the next run: the containers and
host files `homeautomation_teardown` ([vars/main.yml](./vars/main.yml)) lists for it are deleted, such
as the `ping_group_range` sysctl drop-in ESPHome needs. An ha-mcp instance dropped from
`homeautomation_hamcp_instances` has its container removed the same way; its host account is kept, so
a new instance cannot reuse that uid until the account is deleted with `userdel`.

| Not removed               | Why                                                                                                                                                         |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Volumes                   | They hold the only copy of a service's data. Delete by hand, noting that some hold credentials: ESPHome's `secrets.yaml` carries the wifi and OTA passwords |
| Home Assistant, Mosquitto | No flag; always configured                                                                                                                                  |
| Avahi                     | A host package, not a container. Masked, not removed, when a Matter flag is on                                                                              |
| MemryX                    | The DKMS driver and apt sources are not reversed                                                                                                            |
| adb-auto-enable           | It is installed on the sets rather than on this host: `adb uninstall com.tpn.adbautoenable`                                                                 |
| OTBR sysctls              | Forwarding and router-advertisement acceptance stay in `/etc/sysctl.conf` when both Matter flags are cleared                                                |

## OTBR REST API firewall

The OTBR REST API (`homeautomation_otbr_rest_port`) authenticates nobody and exposes the Thread network key. With
either Matter flag on, an nftables table drops TCP to that port unless it arrives on `lo`, without touching Docker's
tables. It is removed when both Matter flags are cleared.

Add the `otbr` integration by hand with the URL `http://127.0.0.1:8081` (or `localhost`): a LAN address is dropped.

## Notes

| Constraint           | Detail                                                                                                                                                                                                                                                                            |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `configuration.yaml` | Hand-maintained per host, except the `frontend:` key: `!include frontend.yaml`, written from [templates/frontend.yaml.j2](./templates/frontend.yaml.j2)                                                                                                                           |
| Frontend modules     | A module in `www/` loads only if `homeautomation_homeassistant_extra_module_urls` names it. Without the entry, every card that depends on it renders as absent and no error is reported                                                                                           |
| Config ownership     | Everything under `config/` is root-owned, so edit through the container: `docker exec homeassistant <cmd>` runs as root with the config at `/config`                                                                                                                              |
| Device paths         | `homeautomation_homeassistant_devices` and a `/dev` `homeautomation_otbr_device` go to Docker unchanged, so name a `/dev/serial/by-id/` link. Docker resolves it at each container start and exposes it at the same path inside, which is the path to configure in Home Assistant |
| `.storage/`          | Home Assistant caches these files and rewrites them on shutdown. Stop it before editing one and start it after, or the edit is overwritten                                                                                                                                        |
| Dashboards           | `.storage/lovelace*`, cached the same way. Prefer [ha-mcp](#ha-mcp)'s `ha_config_set_dashboard`, which writes one without stopping anything and takes effect immediately                                                                                                          |

## Setup

### ha-mcp

1. Generate a long-lived access token in Home Assistant: Profile > Security > Long-lived access tokens > Create token
1. Set `homeautomation_install_hamcp: true` and add an entry to `homeautomation_hamcp_instances` in host vars
1. Run `make homeautomation -- --tags hamcp`, and verify with `docker logs <name>`

### Nginx

Configure reverse proxies with the [letsencrypt_nginx](../letsencrypt_nginx/defaults/main.yml) variables. A site
without `trusted_networks` or `permit_untrusted_networks` answers only localhost (see
[Access control](../letsencrypt_nginx/README.md#access-control)); replace the placeholder CIDR with the LAN's:

```yaml
letsencrypt_nginx_websites:
  # 8971, Frigate's authenticated port. Its unauthenticated one has no login and
  # is bound to loopback for that reason; proxying it publishes the camera UI.
  # 8971 serves TLS, with a self-signed certificate by default.
  - domain: frigate.example.com
    trusted_networks: [192.168.1.0/24]
    proxy_port: 8971
    proxy_https: true
    websocket_paths:
      - /live/jsmpeg
      - /live/mse/api/ws
      - /live/webrtc/api/ws
  - domain: ai.example.com
    trusted_networks: [192.168.1.0/24]
    proxy_port: 3000
    websocket_paths:
      - /ws/socket.io
  - domain: ha.example.com
    trusted_networks: [192.168.1.0/24]
    proxy_port: 8123
    websocket_paths:
      - /api/websocket
```

Home Assistant answers a proxied request with 400 unless `configuration.yaml` sets `http:` `use_x_forwarded_for: true`
and `trusted_proxies: [127.0.0.1, ::1]`: nginx runs on the host network and connects from localhost.

### Android TV adb

Each TV needs a one-time pairing read off its screen. See
[Android TV adb](docs/troubleshooting.md#android-tv-adb).

## Operations

### Home Assistant

```bash
docker exec homeassistant hass --config /config --script check_config
docker exec homeassistant hass --config /config --script check_config --secrets
```

## Documentation

| Document                                           | Contents                                                                                                                              |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| [docs/hardware.md](docs/hardware.md)               | Device setup, Matter pairing, firmware flashing                                                                                       |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Android TV adb, Avahi and Google Cast, EnvisaLink credentials, Frigate, MemryX, Coral.ai, Reolink, entity cleanup, dependency pinning |
| [docs/references.md](docs/references.md)           | Integrations, custom cards, LLM and voice links                                                                                       |
