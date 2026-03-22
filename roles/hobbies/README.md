# ansible-role-hobbies

Installs 3D printing, electronics, and FPV tools on Ubuntu.

## Usage

```bash
make hobbies

ansible-playbook --ask-become-pass hobbies.yml --tags kicad
ansible-playbook --ask-become-pass hobbies.yml --tags orcaslicer
ansible-playbook --ask-become-pass hobbies.yml --tags betaflight
ansible-playbook --ask-become-pass hobbies.yml --tags expresslrs
```

## Features

- **KiCad 9.0** - Electronics schematic and PCB design (with kikit)
- **OrcaSlicer** - 3D printer slicer (AppImage, latest stable from GitHub)
- **Betaflight Configurator** - FPV flight controller configuration (portable build from GitHub)
- **ExpressLRS Configurator** - ExpressLRS radio firmware flashing tool (deb from GitHub)
