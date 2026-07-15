# Troubleshooting

Runbooks for the [homeautomation](../README.md) role.

## Avahi and Google Cast

- [Google Cast with Docker: no Google Cast devices found](https://community.home-assistant.io/t/google-cast-with-docker-no-google-cast-devices-found/145331/24)

Debug with `tcpdump port 5353 -i any` on the host, and `apk add tcpdump && tcpdump port 5353` inside the container.

## EnvisaLink alarm rejects credentials

Log shows `pyenvisalink ... Password is incorrect`, `envisalink` setup aborts, and the alarm panel and zone
sensors disappear (Watchman flags them as missing).

- Keep `envisalink_password` in `secrets.yaml` at **10 characters or fewer**: the module truncates to 10, and a
  longer value passes the web-UI login but fails over the TPI.
- Put the password in `envisalink_password`, not `envisalink_username`/`user_name`.
- `envisalink` is a YAML integration: `docker restart homeassistant` to re-read secrets (a reload will not).

Probe the TPI (port 4025) to see which value the module accepts. It replies `5051…` on success, `5050…` on
rejection; this tests the full password and every shorter prefix:

```bash
docker exec -i homeassistant python3 - <<'PY'
import socket, time, yaml
HOST, PORT = "envisalink.example.com", 4025
pw = yaml.safe_load(open("/config/secrets.yaml"))["envisalink_password"]
cks = lambda s: ("%02X" % (sum(map(ord, s)) & 0xFF))[-2:]
for L in range(len(pw), 3, -1):
    c = pw[:L]
    s = socket.create_connection((HOST, PORT), timeout=6); s.settimeout(4)
    try: s.recv(256)  # 505 login prompt
    except socket.timeout: pass
    s.sendall(("005" + c + cks("005" + c) + "\r\n").encode())
    r = s.recv(256).decode("ascii", "replace"); s.close()
    print(f"len={L:2d} -> {'ACCEPT' if '5051' in r else 'reject'}")
    time.sleep(1)
PY
```

## Frigate restart loop with MemryX

`docker logs frigate` shows:

```text
[error] [Client] No devices in system, please check the server
[DFPRunner] Error in client->init_conenction local mode for device: FIXME
Failed to initialize MemryX model: Init DFP Runner failed!
frigate.watchdog INFO: Detection appears to have stopped. Exiting Frigate...
```

The MemryX kernel module (`memx_cascade_plus_pcie`) is not loaded, so `/dev/memx0` does not exist and the
`mxa-manager` service has no devices. This can happen after a kernel upgrade or reboot.

Verify:

```bash
ls /dev/memx0          # Should exist
lsmod | grep memx      # Should show memx_cascade_plus_pcie
lspci | grep -i memryx # Should show the MX3 PCI device
```

Fix by re-running the memryx tasks, which load the module and restart the manager:

```bash
ansible-playbook --ask-become-pass homeautomation.yml --tags memryx
docker restart frigate
```

Or manually:

```bash
sudo modprobe memx_cascade_plus_pcie
sudo systemctl restart mxa-manager
docker restart frigate
```

## Converting an ONNX model to DFP for MemryX

- [MemryX driver installation](https://github.com/blakeblackshear/frigate/blob/dev/docker/memryx/user_installation.sh).
  The packages are held and will not auto-upgrade
- [MemryX Frigate manual setup](https://devblog.memryx.com/memryx-frigate-manual-setup/)

1. Add the Frigate+ model to Frigate's `config.yml`:

   ```yaml
   model:
     path: plus://<Model ID>
   ```

1. Start Frigate to download the model to `/var/docker-volumes/homeautomation/frigate/config/model_cache/`, then
   stop it.

1. Rename the model file:

   ```bash
   mv <Model ID> 2025-11-04-yolov9s.onnx
   mv <Model ID>.json 2025-11-04-yolov9s.json
   ```

1. Get the model dimensions:

   ```bash
   cat 2025-11-04-yolov9s.json | jq -r '"\(.width),\(.height)"'
   ```

1. Convert to DFP:

   ```bash
   mx_nc --models 2025-11-04-yolov9s.onnx --dfp_fname 2025-11-04-yolov9s.dfp --input_shapes "1,3,320,320" --autocrop --effort hard --num_processes 8 --verbose

   # Monitor for thermal throttling
   watch 'cat /sys/memx0/temperature'

   # Include the newly created "*_post.onnx" file
   zip 2025-11-04-yolov9s.zip 2025-11-04-yolov9s.dfp 2025-11-04-yolov9s_post.onnx
   sudo cp 2025-11-04-yolov9s.zip /var/docker-volumes/homeautomation/frigate/config/
   ```

1. Create a label map:

   ```bash
   cat 2025-11-04-yolov9s.json | jq -r '.labelMap | to_entries[] | "\(.key) \(.value)"' > 2025-11-04-yolov9s.txt
   sudo cp 2025-11-04-yolov9s.txt /var/docker-volumes/homeautomation/frigate/config/
   ```

1. Update Frigate's `config.yml`:

   ```yaml
   model:
     path: /config/2025-11-04-yolov9s.zip
     labelmap_path: /config/2025-11-04-yolov9s.txt
     width: 320
     height: 320
     input_dtype: float
     input_tensor: nchw
     model_type: yolo-generic
   ```

## Coral.ai does not work

- [Failed to load delegate from libedgetpu.so.1.0](https://github.com/blakeblackshear/frigate/issues/3259)

If `docker logs frigate` shows `ValueError: Failed to load delegate from libedgetpu.so.1.0`, reboot or restart
the container.

The Coral.ai USB manufacturer changes from "Global Unichip Corp" to "Google Inc."
[after first inference](https://github.com/google-coral/edgetpu/issues/536). Check with
`lsusb | grep -E 'Global|Google'`.

## Reolink doorbell stops working

When two-way audio is enabled via Frigate, the doorbell chime, quick reply, and siren stop working. Use HTTP-FLV
streams instead of RTSP, disable two-way audio in Frigate, and use the native Reolink integration in Home
Assistant for full doorbell functionality.

- [Frigate discussion #13904](https://github.com/blakeblackshear/frigate/discussions/13904)
- [Reolink camera configuration docs](https://docs.frigate.video/configuration/camera_specific/#reolink-cameras)

```yaml
go2rtc:
  streams:
    doorbell:
      - ffmpeg:https://camera-doorbell.example.com/flv?port=1935&app=bcs&stream=channel0_main.bcs&user={FRIGATE_RTSP_USER}&password={FRIGATE_RTSP_PASSWORD}#audio=copy#video=copy#audio=opus
    doorbell_sub:
      - ffmpeg:https://camera-doorbell.example.com/flv?port=1935&app=bcs&stream=channel0_ext.bcs&user={FRIGATE_RTSP_USER}&password={FRIGATE_RTSP_PASSWORD}
```

## Removing unwanted entities and devices

- [Forum thread](https://community.home-assistant.io/t/remove-leftover-devices-and-entities-from-integration-that-is-uninstalled/316391)

1. Rename unwanted device names and entity IDs to contain `_deprecated`
1. `docker stop homeassistant`
1. Delete entries with `_deprecated` from `./.storage/core.entity_registry` and `core.device_registry`
1. `docker start homeassistant`
1. Run [`recorder.purge_entities`](https://www.home-assistant.io/integrations/recorder/#action-purge_entities)
   with entity_globs set to, for example, `device_tracker.*_deprecated`

Removing MQTT entities:

1. Install [MQTT Explorer](https://mqtt-explorer.com/) and connect to the mosquitto container IP
1. Delete the unwanted topic and its sub-topics under `homeassistant/`

## Pinning a component's dependencies

```bash
docker exec -ti homeassistant \
    bash -c "find /usr/src/homeassistant/ \
    -name 'requirements*.txt' -or -name manifest.json \
    | xargs grep -l pyenvisalink \
    | xargs sed -i 's/pyenvisalink==[a-zA-Z0-9.]\+/pyenvisalink==4.0/g'"
```
