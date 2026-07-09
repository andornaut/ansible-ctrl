# ansible-role-hobbies

Installs 3D printing, electronics, and FPV tools on Ubuntu.

## Usage

```bash
make hobbies

ansible-playbook --ask-become-pass hobbies.yml --tags kicad
```

## Tags

| Tag | Description |
| --- | --- |
| [betaflight](https://github.com/betaflight/betaflight-configurator) | FPV flight controller configurator (latest portable build to `/opt/betaflight/<tag>`, exposed as `/opt/betaflight/current`; `betaflight-configurator` on PATH) |
| [expresslrs](https://github.com/ExpressLRS/ExpressLRS-Configurator) | ExpressLRS radio firmware flashing tool (deb) |
| fpv | Both of the above |
| [freerouting](https://github.com/freerouting/freerouting) | PCB autorouter for KiCad (self-contained linux-x64 build to `/opt/freerouting`; `freerouting` on PATH runs with `-da` to disable analytics); a subset of `kicad` |
| [kicad](https://www.kicad.org/) | Electronics schematic and PCB design (with the [kicad-jlcpcb-tools](https://github.com/Bouni/kicad-jlcpcb-tools) plugin for LCSC part lookup, and [KiKit](https://github.com/yaqwsx/KiKit) in a `/opt/kikit` venv for panelization via splinter-keyboard's `npm run panelize`; git-master build for KiCad 10 support) |
| [orcaslicer](https://github.com/OrcaSlicer/OrcaSlicer) | 3D printer slicer (user flatpak from flathub) |

## Variables

See [defaults/main.yml](./defaults/main.yml). `hobbies_kicad_version` selects both the release PPA and the plugin directory, and `hobbies_user` is the account that user-scoped installs (flatpaks, KiCad plugins) apply to.
