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

Every optional service is also gated on its `homeautomation_install_*` flag, so the tag alone runs nothing.

| Tag | Description |
| --- | --- |
| [adb_auto_enable](https://github.com/mouldybread/adb-auto-enable) | The app that brings adb back on an Android TV, installed on each set from its newest release |
| [avahi](https://avahi.org/) | mDNS discovery service |
| customizations | HA custom components, themes, and www assets |
| docker | All Docker container tasks |
| [esphome](https://esphome.io/) | ESP device firmware and dashboard |
| [frigate](https://github.com/blakeblackshear/frigate) | Video surveillance with AI detection |
| [hamcp](https://github.com/homeassistant-ai/ha-mcp) | Home Assistant MCP server |
| homeassistant | [Home Assistant](https://www.home-assistant.io/) core with [Mosquitto](https://mosquitto.org/) and [Govee2MQTT](https://github.com/wez/govee2mqtt) |
| llm | [llama.cpp](https://github.com/ggml-org/llama.cpp) and [Open WebUI](https://github.com/open-webui/open-webui) |
| matter | [Matter.js](https://github.com/matter-js/matter.js) or [Python Matter Server](https://github.com/matter-js/python-matter-server), and [OTBR](https://openthread.io/guides/border-router) |
| [memryx](https://www.memryx.com/) | GPU accelerator drivers |
| teardown | Remove the containers and host files of components this host does not install |
| voice | [Piper](https://github.com/rhasspy/piper) TTS and [Whisper](https://github.com/OHF-Voice/wyoming-faster-whisper) STT |

## Variables

See [defaults/main.yml](./defaults/main.yml).

### Removing a component

Clearing a `homeautomation_install_*` flag removes the component on the next run: the containers and
host files `homeautomation_teardown` ([vars/main.yml](./vars/main.yml)) lists for it are deleted, such
as the `ping_group_range` sysctl drop-in ESPHome needs.

| Not removed | Why |
| --- | --- |
| Volumes | They hold the only copy of a service's data. Delete by hand, noting that some hold credentials: ESPHome's `secrets.yaml` carries the wifi and OTA passwords |
| Home Assistant, Mosquitto | No flag; always configured |
| Avahi | A host daemon the run stops, not a container |
| MemryX | The DKMS driver and apt sources are not reversed |
| adb-auto-enable | It is installed on the sets rather than on this host: `adb uninstall com.tpn.adbautoenable` |

## Networking

| Mode | Containers | Detail |
| --- | --- | --- |
| host | homeassistant, govee2mqtt, esphome, otbr, the Matter server | Need mDNS or LAN broadcast discovery |
| `homeautomation_default` (`br-ha`) bridge | everything else | Containers reach each other by container name via Docker's DNS. One that must reach a host-networked service uses `extra_hosts: ["host.docker.internal:host-gateway"]` |

Every container is reachable from the Docker host as `{container_name}.internal`, maintained by
[docker_etc_hosts](https://github.com/andornaut/docker_etc_hosts). For a bridge-networked container that name
resolves to its bridge IP, so use the container's **internal** port, not always the published one: openwebui
listens on 8080 and publishes host port 3000. Several publish no host port at all; uncomment their port mappings
in the task files if host-port access is needed.

Task ordering: [docker_prerequisites.yml](./tasks/docker_prerequisites.yml) installs docker_etc_hosts, then
[teardown.yml](./tasks/teardown.yml) releases the names, ports and devices of removed components, then
[docker_homeassistant.yml](./tasks/docker_homeassistant.yml) creates the bridge network, then
[docker_llm.yml](./tasks/docker_llm.yml) (Frigate may depend on llama.cpp). The rest run in any order.

### Container ports

Internal ports. Those that are configurable are `homeautomation_*_port` in
[defaults/main.yml](./defaults/main.yml).

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
| piper | bridge | 10200 | Wyoming | Text-to-speech, also published on the host |
| whisper | bridge | 10300 | Wyoming | Speech-to-text, also published on the host |

### Container hardening

Per-service values are in [defaults/main.yml](./defaults/main.yml); the pattern is:

| Measure | Constraint |
| --- | --- |
| A dedicated host account per container, from [tasks/service_account.yml](./tasks/service_account.yml), with a uid above the range `adduser` allocates from | A file on a bind mount then names the service that wrote it. The uids are in [vars/main.yml](./vars/main.yml), asserted distinct before any account is created. mosquitto follows the uid baked into its image instead |
| `cap_drop: ALL` for every container running as a non-root uid | Such a process cannot use a capability anyway: `cap_add` fills the permitted set, not the ambient set |
| `no-new-privileges` everywhere, root included | It blocks the setuid transition that would make a permitted capability effective |
| Directories closed rather than files, wherever a service rewrites its own state with its own umask | Covers the Zigbee and Thread network keys, the Matter fabric credentials, and the camera configuration and recordings |
| Listeners bound to loopback where nothing off-host consumes them | The MQTT broker allows anonymous access and Frigate serves a second copy of its UI with no login |

### llama.cpp models and context

Router mode (`--models-dir /models`) spawns a child `llama-server` per model with no `--ctx-size`, so each
defaults to 4096 tokens. Two places set what a child runs with:

| Where | Scope | Holds |
| --- | --- | --- |
| `homeautomation_llamacpp_env` | every child, by inheritance | `LLAMA_ARG_CTX_SIZE` for the per-request context, `LLAMA_ARG_N_PARALLEL: "1"` to keep it in one slot rather than split across slots, and `LLAMA_ARG_MODELS_MAX: "1"` for how many children stay resident |
| `homeautomation_llamacpp_model_presets` | one model | any `llama-server` long option, rendered to `/config/models.ini` and passed as `--models-preset`. A section name must match the model id, which the router takes from the file name |

- `LLAMA_ARG_CTX_SIZE` must stay at or below the smallest `homeautomation_llamacpp_models` entry's native
  training context, or quality degrades without YaRN. A model that cannot afford it in VRAM sets a lower `c`
  in its own preset instead.
- KV cache grows with context, and only the full-attention layers hold one: a hybrid model such as
  Qwen3.8-27B, at 16 of 64 layers, needs far less of it per token than its parameter count suggests. Size a
  model as weights + KV against the GPU, and quantize the cache (`cache-type-k`, `cache-type-v`, which need
  `flash-attn = on`) before giving up context. Keep `cache-type-k` the higher precision of the two.
- `LLAMA_ARG_MODELS_MAX: "1"` because one 27B quant plus its cache fills a 16GB GPU. Raising it lets two
  children share the GPU and spill to system RAM; leaving it at 1 costs an unload and reload whenever a
  request names a different model.
- The preset parser rejects some options the command line accepts, `reasoning-effort` and `n-parallel` among
  them (`reasoning` and `reasoning-budget` are taken). A rejected key fails the router at startup, naming the
  option and the section, so the container does not come up.

### Home Assistant conversation agent

Assist talks to llama.cpp through the built-in
[llama.cpp integration](https://www.home-assistant.io/integrations/llama_cpp) (Home Assistant 2026.8 and later):
Settings > Devices & services, URL `http://llamacpp.internal:8080/v1`, the trailing `/v1` required. Router mode
advertises every `homeautomation_llamacpp_models` entry on `/v1/models`, so several agents can run different
models. An agent sees only entities exposed to Assist, and does not fire
[sentence triggers](https://www.home-assistant.io/docs/automation/trigger/#sentence-trigger).

Home Assistant uses host networking, so Docker gives it a **copy** of the host's `/etc/hosts` (see
[moby](https://github.com/moby/moby/blob/master/daemon/container_operations_unix.go)) rather than a mount.
Recreating llamacpp on a different bridge IP therefore leaves Home Assistant on the old address until
`docker restart homeassistant`.

### Matter and Thread

| Constraint | Detail |
| --- | --- |
| Exactly one Matter server | `homeautomation_install_matterjs` or the superseded `homeautomation_install_legacy_pythonmatterserver`, asserted not both |
| The Matter server must use host networking | It discovers Thread devices via the `_matter._tcp` mDNS records OTBR advertises on the LAN, and mDNS multicast does not cross the Docker bridge: a bridged Matter server resolves no node and every Matter device shows unavailable |
| Avahi cannot run alongside Matter/Thread | OTBR and the host-networked Matter server already run mDNS on the host, and a second responder conflicts |

## Operations

### Android TV adb

Home Assistant reaches an Android TV over adb on port 5555, which only exists while the set has wireless
debugging on. [adb-auto-enable](https://github.com/mouldybread/adb-auto-enable) turns it on at boot and moves adbd
off its random ephemeral port onto 5555.

Some sets defeat that by putting the app's `BootReceiver` into the package's `disabledComponents` after every boot,
which takes it out of the `BOOT_COMPLETED` resolution set, so the app never starts. Nothing outside the app can
undo it: `pm enable`, `pm default-state` and `pm enable --user 0` all answer `Shell cannot change component state`
for an app that is not test-only, and `install -r` preserves the disabled state. An app may set its own components,
so the build to run is one that repairs the receiver when its service starts. That is upstream as of
[PR 17](https://github.com/mouldybread/adb-auto-enable/pull/17), released in v0.3.4, so every release from that one
on carries it.

The `adb_auto_enable` tag installs the newest stable release's APK on every set in
`homeautomation_adb_auto_enable_hosts` that does not already carry it, staging the download in a temporary
directory that goes with the run. No pin: a set has no other route to a fix, and an unarmed one costs a pairing
code read off its screen.

The APK's versionName is the release tag without its leading `v`, and a set reports that back through `dumpsys`, so
a set is compared against the release by name.

A set is skipped unless adbd answers a command. The open port is not enough: a set in standby accepts a connection
on 5555 and services nothing behind it, which is why every adb call is wrapped in `timeout` rather than given the
task keyword of that name, a task that times out failing whatever `failed_when` says.

`install -r` keeps the app's data, and with it the app's own adb key, only while the signing key matches what is
installed, and it is refused across a signature change. A set carrying a build signed with another key, a locally
built one among them, needs `adb uninstall` first, and that costs the app's own adb key and the pairing made to it.

| A run finds | What it does |
| --- | --- |
| The newest release already installed | Nothing. The versionName matches, so nothing is downloaded or installed |
| A newer release published | Downloads it and installs over the old one, which keeps the pairing |
| The app absent | Installs, grants, starts it, and reports the pairing code it now needs |
| A set off, or in standby | Skips it. The copy it carries arms itself at its next boot, and a later run reaches it |
| A build signed with another key | Fails, naming the uninstall that clears it |

The app needs its own pairing to move adbd to 5555, and nothing here can do that: the code is shown on the set's
own screen. Read a fresh one at Settings, System, Developer options, Wireless debugging, Pair device with pairing
code, then hand it to the app rather than to `adb pair`:

```bash
curl -X POST --data "port=<port>&code=<code>" http://<tv>:9093/api/pair
curl http://<tv>:9093/api/status     # isPaired true, and currentPort once it has looked
adb shell pm query-receivers --components -a android.intent.action.BOOT_COMPLETED | grep adbautoenable
```

| Gotcha | Detail |
| --- | --- |
| Boot is slow | `BOOT_COMPLETED` reaches the app about five minutes after a reboot on these sets, and adb about a minute after that |
| Wireless debugging does not persist | It is off after every boot, so the app starting is the only thing that brings adb back |
| An unarmed boot needs a person | With the receiver pruned and the app not started, there is no adb to fix it through, and recovery is a pairing code read off the screen |
| Reproducing the prune | Only against a debuggable build, which a release is not: `adb shell run-as com.tpn.adbautoenable pm disable com.tpn.adbautoenable/.BootReceiver` puts it back into the pruned state on demand. `pm disable-user` and `pm disable-until-used` do not apply to a component from the app's own uid |

### Home Assistant

```bash
docker exec homeassistant hass --config /config --script check_config
docker exec homeassistant hass --config /config --script check_config --secrets
```

`configuration.yaml` is hand-maintained per host, except for the `frontend:` key: `!include frontend.yaml`,
written from [templates/frontend.yaml.j2](./templates/frontend.yaml.j2). A module in `www/` loads only if
`homeautomation_homeassistant_extra_module_urls` names it, and a host carrying the file without the entry renders
every card that depends on it as absent, reporting no error.

Everything under `config/` is root-owned, so an edit goes through the container: `docker exec homeassistant <cmd>`
runs as root with the config at `/config`. Home Assistant caches what it keeps in `.storage/` and rewrites those
files on shutdown, so stop it before editing one and start it after, or the edit is overwritten.

Dashboards are `.storage/lovelace*`, and so are cached the same way. Where an [ha-mcp](#ha-mcp)
instance drives the host, `ha_config_set_dashboard` writes one without stopping anything and takes effect
immediately; that is the route to prefer. Editing the file by hand means stopping Home Assistant first.

### Nginx

Configure reverse proxies via the [letsencrypt_nginx](../letsencrypt_nginx/defaults/main.yml) variables:

```yaml
letsencrypt_nginx_websites:
  # 8971, Frigate's authenticated port. Its unauthenticated one has no login and
  # is bound to loopback for that reason; proxying it publishes the camera UI.
  - domain: frigate.example.com
    proxy_port: 8971
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
[Model Context Protocol](https://modelcontextprotocol.io/docs/2026-07-28/getting-started/intro).

1. Generate a long-lived access token in Home Assistant: Profile > Security > Long-lived access tokens > Create token
1. Set `homeautomation_install_hamcp: true` and add an entry to `homeautomation_hamcp_instances` in host vars
1. Run `make homeautomation -- --tags hamcp`, and verify with `docker logs <name>`

Clients connect to `http://<name>.internal:8086/mcp`, the container's internal port on the bridge network.

| Rule | Why |
| --- | --- |
| One instance per Home Assistant an assistant drives, all on the assistant's own host | A remote instance is reached by pointing its `url` at that Home Assistant. The server authenticates nobody, so keeping every instance on the bridge network publishes no MCP port anywhere |
| Each entry needs its own `name` and `uid` | The name becomes both the container name and the service account; the uid must be distinct across every service in this role |

## Documentation

| Document | Contents |
| --- | --- |
| [docs/hardware.md](docs/hardware.md) | Device setup, Matter pairing, firmware flashing |
| [docs/troubleshooting.md](docs/troubleshooting.md) | EnvisaLink credentials, Frigate, MemryX, Coral.ai, entity cleanup |
| [docs/references.md](docs/references.md) | Integrations, custom cards, LLM and voice links |
