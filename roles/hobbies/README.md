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
| [betaflight](https://github.com/betaflight/betaflight-configurator) | FPV flight controller configurator (portable build) |
| [expresslrs](https://github.com/ExpressLRS/ExpressLRS-Configurator) | ExpressLRS radio firmware flashing tool (deb) |
| [kicad](https://www.kicad.org/) | Electronics schematic and PCB design (with [kikit](https://github.com/yaqwsx/KiKit)) |
| [orcaslicer](https://github.com/OrcaSlicer/OrcaSlicer) | 3D printer slicer (AppImage) |
