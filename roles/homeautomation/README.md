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

Every optional service is also gated on its `homeautomation_install_*` flag, so the tag alone installs nothing.
A tag whose flag is off may still remove what an earlier run installed.

| Tag                                                               | Description                                                                                                                                                                              |
| ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [adb_auto_enable](https://github.com/mouldybread/adb-auto-enable) | Installs the newest adb-auto-enable release on each Android TV. See [Android TV adb](docs/troubleshooting.md#android-tv-adb)                                                             |
| [avahi](https://avahi.org/)                                       | mDNS discovery service                                                                                                                                                                   |
| bluetooth                                                         | `bluez`, `dbus-broker` and the AppArmor policy a container needs to reach BLE. No flag; always applied                                                                                   |
| customizations                                                    | HA custom components, themes, and www assets                                                                                                                                             |
| docker                                                            | All Docker container tasks                                                                                                                                                               |
| [esphome](https://esphome.io/)                                    | ESP device firmware and dashboard                                                                                                                                                        |
| [frigate](https://github.com/blakeblackshear/frigate)             | Video surveillance with AI detection                                                                                                                                                     |
| [hamcp](https://github.com/homeassistant-ai/ha-mcp)               | Home Assistant MCP server                                                                                                                                                                |
| homeassistant                                                     | [Home Assistant](https://www.home-assistant.io/) core with [Mosquitto](https://mosquitto.org/) and [Govee2MQTT](https://github.com/wez/govee2mqtt)                                       |
| llm                                                               | [llama.cpp](https://github.com/ggml-org/llama.cpp) and [Open WebUI](https://github.com/open-webui/open-webui)                                                                            |
| matter                                                            | [Matter.js](https://github.com/matter-js/matter.js) or [Python Matter Server](https://github.com/matter-js/python-matter-server), and [OTBR](https://openthread.io/guides/border-router) |
| [memryx](https://memryx.com/)                                     | MemryX MX3 AI accelerator drivers                                                                                                                                                        |
| [mosquitto](https://mosquitto.org/)                               | The MQTT broker's config and its restart. No flag; also applied by `homeassistant`, which defines the container                                                                          |
| otbr                                                              | The host sysctls (IPv4/IPv6 forwarding, router advertisements) the border router needs, gated on either Matter flag. The OTBR container is under `matter`                                |
| router-kva-sample                                                 | The [router kernel address space sampler](#router-kernel-address-space-sampler), gated on `homeautomation_install_router_kva_sample`                                                     |
| teardown                                                          | Remove the containers and host files of components this host does not install                                                                                                            |
| voice                                                             | [Piper](https://github.com/rhasspy/piper) TTS and [Whisper](https://github.com/OHF-Voice/wyoming-faster-whisper) STT                                                                     |

## Variables

See [defaults/main.yml](./defaults/main.yml). The ones that need a decision per host:

| Variable                                                   | Purpose                                                                                                |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `homeautomation_install_*`                                 | One flag per optional service                                                                          |
| `homeautomation_*_uid`                                     | Fixed uid of each container's service account; asserted distinct in [vars/main.yml](./vars/main.yml)   |
| `homeautomation_*_port`                                    | Published host port of a bridge container. The internal port is in [Container ports](#container-ports) |
| `homeautomation_*_bind*`                                   | Listen addresses of the loopback-bound listeners. See [Container hardening](#container-hardening)      |
| `homeautomation_hamcp_instances`                           | One entry per [ha-mcp](#ha-mcp) instance                                                               |
| `homeautomation_otbr_device`, `_backbone_if`               | With Matter: the Thread radio, and the LAN interface (default: the default route's). Asserted          |
| `homeautomation_adb_auto_enable_hosts`                     | The Android TVs that receive adb-auto-enable                                                           |
| `homeautomation_llamacpp_models`, `_env`, `_model_presets` | See [llama.cpp models and context](#llamacpp-models-and-context)                                       |
| `homeautomation_homeassistant_extra_module_urls`           | Frontend modules to load from `www/`. See [Notes](#notes)                                              |
| `homeautomation_router_kva_sample_*`                       | See [Router kernel address space sampler](#router-kernel-address-space-sampler)                        |

## Installed files

| Path                                      | Purpose                                                                     |
| ----------------------------------------- | --------------------------------------------------------------------------- |
| `/usr/local/bin/router-kva-sample`        | [Router kernel address space sampler](#router-kernel-address-space-sampler) |
| `/etc/cron.d/ansible-role-homeautomation` | Its hourly cron entry                                                       |

## Networking

| Mode                                      | Containers                                                  | Detail                                                                                                                                                                 |
| ----------------------------------------- | ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| host                                      | homeassistant, govee2mqtt, esphome, otbr, the Matter server | Need mDNS or LAN broadcast discovery                                                                                                                                   |
| `homeautomation_default` (`br-ha`) bridge | everything else                                             | Containers reach each other by container name via Docker's DNS. One that must reach a host-networked service uses `extra_hosts: ["host.docker.internal:host-gateway"]` |

| Constraint            | Detail                                                                                                                                                                                                                                                                                                                                                                                                  |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `.internal` names     | Every container resolves from the Docker host as `{container_name}.internal`, maintained by [docker_etc_hosts](https://github.com/andornaut/docker_etc_hosts). For a bridge container the name resolves to its bridge IP, so use the internal port: openwebui listens on 8080 and publishes host port 3000                                                                                              |
| Unpublished ports     | Several containers publish no host port. Only llamacpp's task file carries a commented-out mapping to enable for host-port access                                                                                                                                                                                                                                                                       |
| Home Assistant's view | Home Assistant uses host networking, so [tasks/docker_homeassistant.yml](./tasks/docker_homeassistant.yml) bind-mounts the host's `/etc/hosts` read-only. `docker_etc_hosts` overwrites the file in place, so a recreated container's new bridge IP is visible without a restart                                                                                                                        |
| Task order            | [docker_prerequisites.yml](./tasks/docker_prerequisites.yml) installs docker_etc_hosts, then [teardown.yml](./tasks/teardown.yml) releases the names, ports and devices of removed components, then [docker_homeassistant.yml](./tasks/docker_homeassistant.yml) creates the bridge network, then [docker_llm.yml](./tasks/docker_llm.yml) (Frigate may depend on llama.cpp). The rest run in any order |

### Container ports

Internal ports. The `homeautomation_*_port` variables set the published host side of a bridge container's
mapping, not the internal port listed here.

| Container          | Network | Port  | Protocol | Description                                  |
| ------------------ | ------- | ----- | -------- | -------------------------------------------- |
| homeassistant      | host    | 8123  | HTTP     | Web UI and API                               |
| esphome            | host    | 6052  | HTTP     | Dashboard                                    |
| govee2mqtt         | host    | 8056  | HTTP     | Web UI and API; UDP LAN discovery            |
| otbr               | host    | 8080  | HTTP     | Thread Border Router web UI, loopback only   |
| otbr               | host    | 8081  | REST     | Thread Border Router REST API                |
| matterjs           | host    | 5580  | HTTP/WS  | Web UI and WebSocket API, loopback only      |
| pythonmatterserver | host    | 5580  | HTTP/WS  | As matterjs (legacy)                         |
| mosquitto          | bridge  | 1883  | MQTT     | MQTT broker                                  |
| frigate            | bridge  | 5000  | HTTP     | Web UI (unauthenticated), loopback only      |
| frigate            | bridge  | 8971  | HTTP     | Web UI (authenticated), loopback only        |
| frigate            | bridge  | 8554  | RTSP     | RTSP restream, loopback only                 |
| frigate            | bridge  | 8555  | WebRTC   | WebRTC streams                               |
| llamacpp           | bridge  | 8080  | HTTP     | Web UI and OpenAI-compatible API             |
| openwebui          | bridge  | 8080  | HTTP     | Web UI, published on host loopback port 3000 |
| hamcp              | bridge  | 8086  | HTTP     | MCP server                                   |
| piper              | bridge  | 10200 | Wyoming  | Text-to-speech, also on host loopback        |
| whisper            | bridge  | 10300 | Wyoming  | Speech-to-text, also on host loopback        |

## Container hardening

Per-service values are in [defaults/main.yml](./defaults/main.yml).

| Constraint                        | Detail                                                                                                                                                                                                                                                                                                       |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| One host account per container    | Created by [tasks/service_account.yml](./tasks/service_account.yml) with a fixed uid, so a file on a bind mount names the service that wrote it. The uids are collected and asserted distinct in [vars/main.yml](./vars/main.yml) before any account is created. mosquitto uses the uid built into its image |
| `cap_drop: ALL` for non-root uids | A non-root process cannot use a capability: `cap_add` fills the permitted set, not the ambient set                                                                                                                                                                                                           |
| `no-new-privileges` everywhere    | Root included. It blocks the setuid transition that would make a permitted capability effective                                                                                                                                                                                                              |
| Closed directories                | Where a service rewrites its own state with its own umask, the directory is closed, not the files. Covers the Zigbee and Thread network keys, the Matter fabric credentials, and the camera configuration and recordings                                                                                     |
| Loopback listeners                | The MQTT broker, Wyoming, the Matter WebSocket API, the OTBR web UI and Frigate's RTSP restream authenticate nobody, and Frigate's unauthenticated UI has no login, so all bind to loopback. Frigate's authenticated UI and OpenWebUI are reached through the proxy                                          |
| Listeners on every interface      | OTBR's REST API and govee2mqtt's HTTP API: both images hard-code the listen address                                                                                                                                                                                                                          |
| Frigate RTSP from the LAN         | A Frigate integration whose `rtsp_url_template` names the host's LAN address needs `homeautomation_frigate_bind_rtsp: "0.0.0.0"`                                                                                                                                                                             |

## llama.cpp models and context

Router mode (`--models-dir /models`) starts a child `llama-server` per model with no `--ctx-size`, so each
defaults to 4096 tokens. Two variables set what a child runs with:

| Variable                                | Scope                       | Holds                                                                                                                                                                               |
| --------------------------------------- | --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `homeautomation_llamacpp_env`           | every child, by inheritance | `LLAMA_ARG_CTX_SIZE` for the per-request context, `LLAMA_ARG_N_PARALLEL: "1"` to keep it in one slot, and `LLAMA_ARG_MODELS_MAX: "1"` for how many children stay resident           |
| `homeautomation_llamacpp_model_presets` | one model                   | Any `llama-server` long option, rendered to `/config/models.ini` and passed as `--models-preset`. A section name must match the model id, which the router takes from the file name |

| Constraint             | Detail                                                                                                                                                                                                                                                                             |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Context ceiling        | `LLAMA_ARG_CTX_SIZE` must not exceed the smallest `homeautomation_llamacpp_models` entry's native training context, or quality degrades without YaRN. A model that cannot fit it in VRAM sets a lower `c` in its own preset                                                        |
| KV cache sizing        | Only full-attention layers hold KV cache: a hybrid model such as Qwen3.8-27B, at 16 of 64 layers, needs far less per token than its parameter count suggests. Size a model as weights + KV against the GPU                                                                         |
| Cache quantization     | Quantize the cache (`cache-type-k`, `cache-type-v`, which need `flash-attn = on`) before reducing context. Keep `cache-type-k` the higher precision of the two                                                                                                                     |
| `LLAMA_ARG_MODELS_MAX` | `1` because one 27B quant plus its cache fills a 16GB GPU. Raising it lets two children share the GPU and spill to system RAM; at 1 a request naming a different model costs an unload and reload                                                                                  |
| Preset keys            | The preset parser rejects some options the command line accepts, `reasoning-effort` and `n-parallel` among them (`reasoning` and `reasoning-budget` are accepted). A rejected key fails the router at startup, naming the option and the section, and the container does not start |

### Conversation agent

Assist talks to llama.cpp through the built-in
[llama.cpp integration](https://www.home-assistant.io/integrations/llama_cpp) (Home Assistant 2026.8 and later):
Settings > Devices & services, URL `http://llamacpp.internal:8080/v1`, the trailing `/v1` required. Router mode
lists every `homeautomation_llamacpp_models` entry on `/v1/models`, so several agents can run different models. An
agent sees only entities exposed to Assist, and does not fire
[sentence triggers](https://www.home-assistant.io/docs/automation/trigger/#sentence-trigger).

## Matter and Thread

| Constraint                                 | Detail                                                                                                                                                                                                                              |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Exactly one Matter server                  | `homeautomation_install_matterjs` or the superseded `homeautomation_install_legacy_pythonmatterserver`, asserted not both                                                                                                           |
| The Matter server must use host networking | It discovers Thread devices via the `_matter._tcp` mDNS records OTBR advertises on the LAN, and mDNS multicast does not cross the Docker bridge: a bridged Matter server resolves no node and every Matter device shows unavailable |
| Avahi cannot run alongside Matter/Thread   | OTBR and the host-networked Matter server already run mDNS on the host, and a second responder conflicts                                                                                                                            |

## ha-mcp

[ha-mcp](https://github.com/homeassistant-ai/ha-mcp) exposes Home Assistant to AI assistants over the
[Model Context Protocol](https://modelcontextprotocol.io/docs/2026-07-28/getting-started/intro). Clients connect to
`http://<name>.internal:8086/mcp`, the container's internal port on the bridge network. Setup is under
[Setup](#setup).

| Constraint                                                                           | Detail                                                                                                                                                                                     |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| One instance per Home Assistant an assistant drives, all on the assistant's own host | A remote instance is reached by pointing its `url` at that Home Assistant. The server authenticates nobody, so keeping every instance on the bridge network publishes no MCP port anywhere |
| Each entry needs its own `name` and `uid`                                            | The name becomes both the container name and the service account; the uid must be distinct across every service in this role                                                               |

## Router kernel address space sampler

`homeautomation_install_router_kva_sample` installs `/usr/local/bin/router-kva-sample` and an hourly cron entry
that reads `vm.kvm_free` from a pfSense router over ssh and writes it to
`homeautomation_router_kva_sample_entity_id`. It takes a token from the
`homeautomation_router_kva_sample_container` container, so none is written to disk.

It is in this role, not the [router](../router/README.md) role, because it runs on this host, needs the ha-mcp
container this role installs, and writes a Home Assistant entity.

| Constraint                                      | Detail                                                                                                                                                                                                                                                                                                                                                                |
| ----------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Runs as `homeautomation_router_kva_sample_user` | The key that reaches the router and the docker group that reads the token belong to that account. Root's ssh configuration on this host is hand-maintained, not provisioned here                                                                                                                                                                                      |
| 32-bit routers only                             | A pfSense router's kernel map only advances: the figure falls over an uptime and freed memory returns none of it. At zero every `pfctl -f` blocks in the kernel arena wait channel and rule changes stop loading while the running ruleset keeps filtering. No error is reported, and only a reboot clears it. An amd64 router has a 2 TiB map and never reaches zero |
| Unchanged readings                              | Posting an identical state and attributes returns 200 and updates neither `last_changed` nor `last_reported`, so a working sampler shows as stale in the UI while the figure is steady                                                                                                                                                                                |
| Threshold                                       | Set in a Home Assistant automation, not here                                                                                                                                                                                                                                                                                                                          |

## Removing a component

Clearing a `homeautomation_install_*` flag removes the component on the next run: the containers and
host files `homeautomation_teardown` ([vars/main.yml](./vars/main.yml)) lists for it are deleted, such
as the `ping_group_range` sysctl drop-in ESPHome needs. An ha-mcp instance dropped from
`homeautomation_hamcp_instances` has its container removed the same way.

| Not removed               | Why                                                                                                                                                         |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Volumes                   | They hold the only copy of a service's data. Delete by hand, noting that some hold credentials: ESPHome's `secrets.yaml` carries the wifi and OTA passwords |
| Home Assistant, Mosquitto | No flag; always configured                                                                                                                                  |
| Avahi                     | A host daemon the run stops, not a container                                                                                                                |
| MemryX                    | The DKMS driver and apt sources are not reversed                                                                                                            |
| adb-auto-enable           | It is installed on the sets rather than on this host: `adb uninstall com.tpn.adbautoenable`                                                                 |

## Notes

| Constraint           | Detail                                                                                                                                                                                  |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `configuration.yaml` | Hand-maintained per host, except the `frontend:` key: `!include frontend.yaml`, written from [templates/frontend.yaml.j2](./templates/frontend.yaml.j2)                                 |
| Frontend modules     | A module in `www/` loads only if `homeautomation_homeassistant_extra_module_urls` names it. Without the entry, every card that depends on it renders as absent and no error is reported |
| Config ownership     | Everything under `config/` is root-owned, so edit through the container: `docker exec homeassistant <cmd>` runs as root with the config at `/config`                                    |
| `.storage/`          | Home Assistant caches these files and rewrites them on shutdown. Stop it before editing one and start it after, or the edit is overwritten                                              |
| Dashboards           | `.storage/lovelace*`, cached the same way. Prefer [ha-mcp](#ha-mcp)'s `ha_config_set_dashboard`, which writes one without stopping anything and takes effect immediately                |

## Setup

### ha-mcp

1. Generate a long-lived access token in Home Assistant: Profile > Security > Long-lived access tokens > Create token
1. Set `homeautomation_install_hamcp: true` and add an entry to `homeautomation_hamcp_instances` in host vars
1. Run `make homeautomation -- --tags hamcp`, and verify with `docker logs <name>`

### Nginx

Configure reverse proxies with the [letsencrypt_nginx](../letsencrypt_nginx/defaults/main.yml) variables:

```yaml
letsencrypt_nginx_websites:
  # 8971, Frigate's authenticated port. Its unauthenticated one has no login and
  # is bound to loopback for that reason; proxying it publishes the camera UI.
  - domain: frigate.example.com
    proxy_port: 8971
    websocket_paths:
      - /live/jsmpeg
      - /live/mse/api/ws
      - /live/webrtc/api/ws
  - domain: ai.example.com
    proxy_port: 3000
    websocket_paths:
      - /ws/socket.io
  - domain: ha.example.com
    proxy_port: 8123
    websocket_paths:
      - /api/websocket
```

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
