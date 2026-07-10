# Hardware

Device-specific setup, pairing, and firmware notes for the [homeautomation](../README.md) role.

## Matter and Thread pairing

Prerequisites:

- A Thread Border Router, such as the [Home Assistant Connect ZBT-1](#home-assistant-connect-zbt-1)
- Matter devices and controllers on the same L2 network
- IPv6 networking enabled; link-local addresses are sufficient

Steps:

1. Factory reset the device, per the device sections below
1. In the Home Assistant mobile app, go to Settings > Devices & Services > Matter > Add device > No. It's new
1. Scan the QR code on the device with the mobile app
1. Wait for commissioning to complete

### Pairing from a different subnet

If the phone's WiFi network is on a different subnet than the Thread Border Router, pairing fails during device
discovery. A USB-C ethernet adapter that temporarily puts the phone on the same LAN works around it. Replace
steps 2 to 4 above with:

1. In the Home Assistant mobile app, go to Settings > Devices & Services > Matter > Add device > No. It's new
1. Scan the device's QR code
1. Plug the ethernet adapter into the phone
1. Wait approximately 4 seconds, then tap "I'm ready"

The timing is load-bearing. The pairing flow runs a WiFi connectivity check before the "I'm ready" prompt, and
starts mDNS discovery after it. Plug the ethernet adapter in before tapping "I'm ready", so the connectivity
check passes over WiFi while discovery occurs on the ethernet LAN.

## Devices

### AirGradient

- [Official website](https://www.airgradient.com/) and [dashboard](https://app.airgradient.com/dashboard)
- [Official Home Assistant integration](https://www.home-assistant.io/integrations/airgradient)
- [Alternative Home Assistant integration](https://github.com/MallocArray/airgradient_esphome)

Setup:

1. [Install ESPHome](https://esphome.io/guides/installing_esphome#linux)
1. Download [airgradient-one.yaml](https://raw.githubusercontent.com/MallocArray/airgradient_esphome/refs/heads/main/airgradient-one.yaml)
1. Set `name` and `friendly_name`, and add WiFi credentials
1. Run `esphome run airgradient-one.yaml`
1. Add the device via the ESPHome integration in Home Assistant

### AMD GPU

Make `/dev/kfd` (AMD GPU compute) writable from within a container. See
[AMD GPU driver installation](https://github.com/andornaut/til/blob/master/docs/ubuntu.md#install-amd-gpu-dkms-kernel-module-driver).

Edit `/etc/udev/rules.d/70-amdgpu.rules`:

```text
KERNEL=="kfd", GROUP="video", MODE="0660"
```

```bash
sudo udevadm control --reload
sudo udevadm trigger
```

### Bluetooth

- [dbus-broker](https://github.com/bus1/dbus-broker/wiki)
- [Home Assistant bluetooth integration](https://www.home-assistant.io/integrations/bluetooth)

M5Stack bluetooth proxy:

1. Plug in the [M5Stack](https://www.aliexpress.com/item/1005003299215808.html) via USB
1. Navigate to [ESPHome bluetooth proxy installation](https://esphome.io/projects/index.html) in Chrome
1. Select "Bluetooth proxy" > "M5Stack", connect, install, and configure WiFi
1. Add the new ESPHome device in Home Assistant

### Coral.ai USB Accelerator

- [Product page](https://coral.ai/products/accelerator/)

### Eve Door & Window Contact Sensor

- [Product page](https://www.evehome.com/en-us/eve-door-window) and
  [support](https://www.evehome.com/en-us/support/eve-door-window)
- Factory reset: open the battery compartment and press the reset button with a paperclip until the red LED blinks

### Eve Energy Outlet (In-Wall, 10ECN4151 / 20ECN4101)

- [Product page](https://www.evehome.com/en-us/eve-energy-outlet) and
  [support](https://www.evehome.com/en-us/support/eve-energy)
- Factory reset: press the right LED for 10 seconds

### Home Assistant Connect ZBT-1

- [Official documentation](https://connectzbt1.home-assistant.io/)
- [Thread](https://www.home-assistant.io/integrations/thread/#list-of-thread-border-router-devices) and
  [enabling Thread support](https://support.nabucasa.com/hc/en-us/articles/26124710072861-Enabling-Thread-support)

### Inovelli White Series Switch

- [Product page](https://inovelli.com/products/thread-matter-white-series-smart-2-1-on-off-dimmer-switch) and
  [setup instructions](https://help.inovelli.com/en/articles/9692499-white-series-dimmer-switch-setup-instructions-home-assistant)
- Factory reset: hold the top paddle (on) and the config/favorites button (above the LED) for 20 seconds, until
  the LED bar turns red and blinks 3 times
- Pairing mode: the LED bar should pulse blue automatically after reset. If not, tap the config/favorites button
  3 times quickly

### ratgdo (garage door opener)

- [ratgdo](https://paulwieland.github.io/ratgdo/)
- [Alternative hardware](https://www.gelidus.ca/product/gelidus-research-ratgdo-alternative-board-v2-usb-c/)

Setup:

1. Flash the [MQTT firmware](https://github.com/ratgdo/mqtt-ratgdo) using the
   [web installer](https://paulwieland.github.io/ratgdo/flash.html), or the
   [ESPHome firmware](https://ratgdo.github.io/esphome-ratgdo/)
1. Set the MQTT IP and port (1883) in the admin web interface. Use an IP, not a hostname
1. Wire the ratgdo according to [this diagram](https://user-images.githubusercontent.com/4663918/276749741-fe82ea10-e8f4-41d6-872f-55eec88d2aab.png)
1. Add the device in Home Assistant > Settings > Devices & services

### Roborock vacuums

- [Commands](https://github.com/marcelrv/XiaomiRobotVacuumProtocol?tab=readme-ov-file)
- [Mop control](https://community.home-assistant.io/t/s7-mop-control/317393/42)

[Custom mode](https://github.com/marcelrv/XiaomiRobotVacuumProtocol/blob/master/custom_mode.md):

| Mode | Description |
| --- | --- |
| 101 | Silent |
| 102 | Balanced |
| 103 | Turbo |
| 104 | Max |
| 105 | Off (mop only) |
| 106 | Custom (Auto) |

[Water box custom mode](https://github.com/marcelrv/XiaomiRobotVacuumProtocol/blob/master/water_box_custom_mode.md#set-water-box-custom-mode):

| Mode | Flow level |
| --- | --- |
| 200 | Off |
| 201 | Low |
| 202 | Medium |
| 203 | High |
| 204 | Custom (Auto) |
| 207 | Custom (Levels) |

Mop mode:

| Mode | Description |
| --- | --- |
| 300 | Standard |
| 301 | Deep |
| 302 | Custom |
| 303 | Deep+ |

### Sensi thermostat

Setup via HomeKit:

1. Reset the thermostat to factory settings
1. Begin setup via the Sensi app
1. Note the pairing code displayed before configuring WiFi
1. Complete WiFi setup via Sensi, then switch to Home Assistant
1. Add the new HomeKit device in Home Assistant using the noted pairing code
1. Complete the Sensi app setup

### SMLight SLZB-MR1U

- [AliExpress](https://www.aliexpress.com/item/1005008814854495.html)
- [Setup and review](https://smarthomescene.com/reviews/smlight-slzb-mr1-multi-radio-coordinator-setup-and-review/)
- [SMLIGHT manuals](https://smlight.tech/support/manuals/books/slzb-os/page/zigbee2mqtt-zha-settings)

The SLZB-MR1U has two radios: Zigbee (CC2652P7, port 7638) and Thread (EFR32MG21, port 6638).

ZHA setup:

1. Open the SLZB-MR1U web UI and confirm the Zigbee radio is in coordinator mode
1. Leave "Zigbee Hub Mode" disabled, since Hub Mode makes the SLZB a standalone hub, bypassing ZHA
1. In Home Assistant: Settings > Devices & Services > Add Integration > ZHA
1. Radio type: **ZNP** (TI CC2652P7 chip)
1. Serial port path: `socket://<SLZB-IP>:7638`

### SONOFF Zigbee 3.0 USB Dongle Plus (CC2652P)

- [Firmware](https://github.com/Koenkk/Z-Stack-firmware/)
- [Instructions](https://sonoff.tech/wp-content/uploads/2023/02/SONOFF-Zigbee-3.0-USB-dongle-plus-firmware-flashing.pdf)
- [Flashing via cc2538-bsl](https://www.zigbee2mqtt.io/guide/adapters/flashing/flashing_via_cc2538-bsl.html)

```bash
docker stop homeassistant
docker run --rm \
    --device /dev/ttyUSB0:/dev/ttyUSB0 \
    -e FIRMWARE_URL=https://github.com/Koenkk/Z-Stack-firmware/raw/master/coordinator/Z-Stack_3.x.0/bin/CC1352P2_CC2652P_launchpad_coordinator_20230507.zip \
    ckware/ti-cc-tool -ewv -p /dev/ttyUSB0 --bootloader-sonoff-usb
```
