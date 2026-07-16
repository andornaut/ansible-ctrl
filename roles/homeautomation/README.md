# ansible-role-homeautomation

Provisions [Home Assistant](https://www.home-assistant.io/) and the related services listed under
[Tags](#tags) as Docker containers.

[![homeassistant](https://raw.githubusercontent.com/andornaut/homeassistant-ibm1970-theme/main/screenshots/dark-colors-small.png)](https://github.com/andornaut/homeassistant-ibm1970-theme/blob/main/screenshots/dark-colors.png)

## Usage

```bash
make homeautomation
make homeautomation -- --tags frigate
```

## Tags

| Tag | Description |
| --- | --- |
| [avahi](https://avahi.org/) | mDNS discovery service |
| customizations | HA custom components, themes, and www assets |
| docker | All Docker container tasks |
| [esphome](https://esphome.io/) | ESP device firmware and dashboard |
| [frigate](https://github.com/blakeblackshear/frigate) | Video surveillance with AI detection |
| [hamcp](https://github.com/homeassistant-ai/ha-mcp) | Home Assistant MCP server |
| homeassistant | [Home Assistant](https://www.home-assistant.io/) core with [Mosquitto](https://mosquitto.org/) and [Govee2MQTT](https://github.com/wez/govee2mqtt) |
| llm | [llama.cpp](https://github.com/ggml-org/llama.cpp) and [Open WebUI](https://github.com/open-webui/open-webui) |
| matter | [Matter.js](https://github.com/project-chip/matter.js) or [Python Matter Server](https://github.com/home-assistant-libs/python-matter-server), and [OTBR](https://openthread.io/guides/border-router) |
| [memryx](https://www.memryx.com/) | GPU accelerator drivers |
| voice | [Piper](https://github.com/rhasspy/piper) TTS and [Whisper](https://github.com/rhasspy/wyoming-whisper) STT |

## Variables

See [defaults/main.yml](./defaults/main.yml).

## Networking

Containers use one of two network modes:

- **Host networking**, for containers that need mDNS or LAN broadcast discovery: homeassistant, govee2mqtt,
  esphome, otbr, and the Matter server. They bind directly to the host.
- **The `homeautomation_default` (`br-ha`) bridge** for everything else, where containers reach each other by
  container name via Docker's DNS. Those that need to reach a host-networked service use
  `extra_hosts: ["host.docker.internal:host-gateway"]`.

Every container is reachable from the Docker host as `{container_name}.internal`, maintained by
[docker_etc_hosts](https://github.com/andornaut/docker_etc_hosts). For a bridge-networked container that name
resolves to its bridge IP, so use the container's **internal** port, which is not always the published one:
openwebui listens on 8080 and publishes host port 3000. Most publish no host port at all; uncomment their port
mappings in the task files if host-port access is needed.

Task ordering: [docker_prerequisites.yml](./tasks/docker_prerequisites.yml) installs docker_etc_hosts, then
[docker_homeassistant.yml](./tasks/docker_homeassistant.yml) creates the bridge network, then
[docker_llm.yml](./tasks/docker_llm.yml) (Frigate may depend on llama.cpp). The rest run in any order.

### Container ports

| Container | Network | Port | Protocol | Description |
| --- | --- | --- | --- | --- |
| homeassistant | host | 8123 | HTTP | Web UI and API |
| esphome | host | 6052 | HTTP | Dashboard |
| govee2mqtt | host | none | UDP | LAN broadcast discovery |
| otbr | host | 8080 | HTTP | Thread Border Router web UI |
| otbr | host | 8081 | REST | Thread Border Router REST API |
| matterjs | host | 5580 | HTTP/WS | Web UI and WebSocket API |
| pythonmatterserver | host | 5580 | HTTP/WS | Web UI and WebSocket API (legacy) |
| mosquitto | bridge | 1883 | MQTT | MQTT broker |
| frigate | bridge | 5000 | HTTP | Web UI (unauthenticated) |
| frigate | bridge | 8971 | HTTP | Web UI (authenticated) |
| frigate | bridge | 8554 | RTSP | RTSP streams |
| frigate | bridge | 8555 | WebRTC | WebRTC streams |
| llamacpp | bridge | 8080 | HTTP | Web UI and OpenAI-compatible API |
| openwebui | bridge | 8080 | HTTP | Web UI, published on host port 3000 |
| hamcp | bridge | 8086 | HTTP | MCP server |
| piper | bridge | 10200 | Wyoming | Text-to-speech |
| whisper | bridge | 10300 | Wyoming | Speech-to-text |

### llama.cpp models and context

Router mode (`--models-dir /models`) spawns a child `llama-server` per model with no `--ctx-size`, so each
defaults to 4096 tokens. `homeautomation_llamacpp_env` sets vars the children inherit: `LLAMA_ARG_CTX_SIZE` for
the per-request context and `LLAMA_ARG_N_PARALLEL: "1"` to keep it in one slot (else it is split across slots).

`LLAMA_ARG_CTX_SIZE` must stay at or below the smallest model's native training context or quality degrades
without YaRN: Qwen3.5-9B is 262144, gemma-4-E4B is 131072, so 131072 is the shared ceiling. KV cache grows with
context; at 128k these models exceed the 16GB GPU and spill to system RAM. Lower it if latency or memory is a
problem.

### Matter and Thread

- Enable exactly one Matter server, `homeautomation_install_matterjs` or the superseded
  `homeautomation_install_legacy_pythonmatterserver`. The role asserts that both are not enabled at once.
- **The Matter server must use host networking.** It discovers Thread devices via the `_matter._tcp` mDNS records
  OTBR advertises on the LAN, and mDNS multicast does not cross the Docker bridge, so a bridged Matter server never
  resolves any node and every Matter device shows as unavailable.
- **Avahi cannot run alongside Matter/Thread**, because OTBR and the host-networked Matter server already run mDNS
  on the host and a second responder conflicts.

## Operations

### Home Assistant

```bash
docker exec homeassistant hass --config /config --script check_config
docker exec homeassistant hass --config /config --script check_config --secrets
```

### Nginx

Configure reverse proxies via the [letsencrypt_nginx](../letsencrypt_nginx/defaults/main.yml) variables:

```yaml
letsencrypt_nginx_websites:
  - domain: frigate.example.com
    proxy_port: 5000
    websocket_enabled: true
  - domain: ai.example.com
    proxy_port: 3000
    websocket_path: /ws/socket.io
  - domain: ha.example.com
    proxy_port: 8123
    websocket_path: /api/websocket
```

### ha-mcp

[ha-mcp](https://github.com/homeassistant-ai/ha-mcp) exposes Home Assistant to AI assistants over the
[Model Context Protocol](https://modelcontextprotocol.io/).

1. Generate a long-lived access token in Home Assistant: Profile > Security > Long-lived access tokens > Create token
1. Set `homeautomation_install_hamcp: true` and `homeautomation_hamcp_token` in host vars
1. Run `make homeautomation -- --tags hamcp`, and verify with `docker logs hamcp`

Clients connect to `http://hamcp.internal:8086/mcp`: the container's internal port on the bridge network, not a
host-mapped port. It is configured for VSCode in this project's `.vscode/mcp.json`, and under `mcpServers` in
`~/.claude.json` for Claude Code.

## Documentation

| Document | Contents |
| --- | --- |
| [docs/hardware.md](docs/hardware.md) | Device setup, Matter pairing, firmware flashing |
| [docs/troubleshooting.md](docs/troubleshooting.md) | EnvisaLink credentials, Frigate, MemryX, Coral.ai, entity cleanup |
| [docs/references.md](docs/references.md) | Integrations, custom cards, LLM and voice links |
