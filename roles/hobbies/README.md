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
| [betaflight](https://github.com/betaflight/betaflight-configurator) | FPV flight controller configurator |
| [expresslrs](https://github.com/ExpressLRS/ExpressLRS-Configurator) | ExpressLRS radio firmware flashing tool (deb) |
| fpv | betaflight and expresslrs |
| [freerouting](https://github.com/freerouting/freerouting) | PCB autorouter for KiCad; a subset of `kicad` |
| [kicad](https://www.kicad.org/) | Electronics schematic and PCB design, with plugins |
| [orcaslicer](https://github.com/OrcaSlicer/OrcaSlicer) | 3D printer slicer (user flatpak from flathub) |

## Variables

See [defaults/main.yml](./defaults/main.yml).

| Variable | Purpose |
| --- | --- |
| `hobbies_kicad_version` | Selects both the release PPA and the plugin directory |
| `hobbies_user` | Account that user-scoped installs (flatpaks, KiCad plugins) apply to |

## Notes

- betaflight installs the latest portable build to `/opt/betaflight/<tag>`, exposed as `/opt/betaflight/current`,
  with `betaflight-configurator` on PATH.
- freerouting installs the self-contained linux-x64 build to `/opt/freerouting`. The `freerouting` wrapper on
  PATH passes `-da` to disable analytics.
- kicad is a git-master build, for KiCad 10 support. It installs the
  [kicad-jlcpcb-tools](https://github.com/Bouni/kicad-jlcpcb-tools) plugin for LCSC part lookup, and
  [KiKit](https://github.com/yaqwsx/KiKit) in a `/opt/kikit` venv for panelization via splinter-keyboard's
  `npm run panelize`.
