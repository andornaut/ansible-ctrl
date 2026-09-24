# Troubleshooting

Runbooks for the [homeautomation](../README.md) role.

## Android TV adb

Home Assistant reaches an Android TV over adb on port 5555, which exists only while the TV has wireless debugging
on. [adb-auto-enable](https://github.com/mouldybread/adb-auto-enable) turns wireless debugging on at boot and moves
adbd from its random ephemeral port to 5555. The `adb_auto_enable` tag installs it on every TV in
`homeautomation_adb_auto_enable_hosts`.

| Constraint                            | Detail                                                                                                                                                                                                                                                                                        |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Pruned `BootReceiver`                 | Some TVs add the app's `BootReceiver` to the package's `disabledComponents` after every boot, which removes it from the `BOOT_COMPLETED` resolution set, so the app never starts                                                                                                              |
| Only the app can re-enable it         | `pm enable`, `pm default-state` and `pm enable --user 0` all answer `Shell cannot change component state` for an app that is not test-only, and `install -r` preserves the disabled state. v0.3.4 and later repair the receiver when the service starts                                       |
| No version pin                        | The tag installs the newest stable release's APK on every TV that does not already have it, staging the download in a temporary directory removed at the end of the run. A TV has no other way to receive a fix, and one that does not start the app needs a pairing code read off its screen |
| Version comparison                    | The APK's versionName is the release tag without its leading `v`, and the TV reports it through `dumpsys`, so a TV is compared against the release by name                                                                                                                                    |
| Standby TVs are skipped               | A TV is skipped unless adbd answers a command. A TV in standby accepts a connection on 5555 and does not respond behind it. Every adb call is wrapped in `timeout`, not the task keyword of that name: a task that times out fails whatever `failed_when` says                                |
| Signing key changes                   | `install -r` keeps the app's data, including the app's own adb key, only while the signing key matches, and is refused across a signature change. A TV with a build signed by another key, a local build included, needs `adb uninstall` first, which loses the app's adb key and its pairing |
| Boot is slow                          | `BOOT_COMPLETED` reaches the app about five minutes after a reboot on these TVs, and adb is available about a minute after that                                                                                                                                                               |
| Wireless debugging does not persist   | It is off after every boot, so the app starting is the only thing that re-enables adb                                                                                                                                                                                                         |
| A boot without the app needs a person | With the receiver pruned and the app not started, there is no adb to fix it through. Recovery is a pairing code read off the screen                                                                                                                                                           |
| Reproducing the prune                 | Only against a debuggable build, which a release is not: `adb shell run-as com.tpn.adbautoenable pm disable com.tpn.adbautoenable/.BootReceiver` disables the receiver on demand. `pm disable-user` and `pm disable-until-used` do not apply to a component from the app's own uid            |

| A run finds                          | Result                                                                                |
| ------------------------------------ | ------------------------------------------------------------------------------------- |
| The newest release already installed | Nothing. The versionName matches, so nothing is downloaded or installed               |
| A newer release published            | Downloads it and installs over the old one, which keeps the pairing                   |
| The app absent                       | Installs, grants and starts it. It then needs a pairing code                          |
| A TV off, or in standby              | Skips it. The installed copy starts at the TV's next boot, and a later run reaches it |
| A build signed with another key      | Fails, naming the uninstall that clears it                                            |

The app needs its own pairing to move adbd to 5555, and the code is shown only on the TV's screen. Read a new one
at Settings, System, Developer options, Wireless debugging, Pair device with pairing code, and send it to the app,
not to `adb pair`:

```bash
curl -X POST --data "port=<port>&code=<code>" http://<tv>:9093/api/pair
curl http://<tv>:9093/api/status     # isPaired true, and currentPort once it has checked
adb shell pm query-receivers --components -a android.intent.action.BOOT_COMPLETED | grep adbautoenable
```

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
`mxa-manager` service has no devices, which can follow a kernel upgrade or a reboot.

Verify:

```bash
ls /dev/memx0          # Should exist
lsmod | grep memx      # Should show memx_cascade_plus_pcie
lspci | grep -i memryx # Should show the MX3 PCI device
```

Fix by re-running the memryx tasks, which load the module and restart the manager:

```bash
make homeautomation -- --tags memryx
docker restart frigate
```

Or by hand:

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

1. Name the model, and use that name for every file below. Dating it keeps successive conversions distinct:

   ```bash
   MODEL=$(date +%F)-yolov9s
   CONFIG=/var/docker-volumes/homeautomation/frigate/config
   mv <Model ID> $MODEL.onnx
   mv <Model ID>.json $MODEL.json
   ```

1. Get the model dimensions, which the conversion and Frigate's config both need:

   ```bash
   jq -r '"\(.width),\(.height)"' $MODEL.json
   ```

1. Convert to DFP, substituting those dimensions into `--input_shapes`:

   ```bash
   mx_nc --models $MODEL.onnx --dfp_fname $MODEL.dfp --input_shapes "1,3,320,320" \
       --autocrop --effort hard --num_processes 8 --verbose

   # Monitor for thermal throttling
   watch 'cat /sys/memx0/temperature'

   # Include the newly created "*_post.onnx" file
   zip $MODEL.zip $MODEL.dfp ${MODEL}_post.onnx
   sudo cp $MODEL.zip $CONFIG/
   ```

1. Create a label map:

   ```bash
   jq -r '.labelMap | to_entries[] | "\(.key) \(.value)"' $MODEL.json > $MODEL.txt
   sudo cp $MODEL.txt $CONFIG/
   ```

1. Update Frigate's `config.yml`, with the name and dimensions from above:

   ```yaml
   model:
     path: /config/<model>.zip
     labelmap_path: /config/<model>.txt
     width: 320
     height: 320
     input_dtype: float
     input_tensor: nchw
     model_type: yolo-generic
   ```

## Coral.ai does not work

- [Failed to load delegate from libedgetpu.so.1.0](https://github.com/blakeblackshear/frigate/issues/3259)

If `docker logs frigate` shows `ValueError: Failed to load delegate from libedgetpu.so.1.0`, reboot or restart
the container. The Coral.ai USB manufacturer changes from "Global Unichip Corp" to "Google Inc."
[after first inference](https://github.com/google-coral/edgetpu/issues/536), so
`lsusb | grep -E 'Global|Google'` says whether it has run.

## Reolink doorbell stops working

When two-way audio is enabled via Frigate, the doorbell chime, quick reply, and siren stop working. Use HTTP-FLV
streams instead of RTSP, disable two-way audio in Frigate, and drive the doorbell through the native Reolink
integration.

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
