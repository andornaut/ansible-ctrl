# ansible-role-hobbies

Installs 3D printing, electronics, and FPV tools on Ubuntu.

## Usage

```bash
make hobbies
make hobbies -- --tags kicad
```

## Tags

| Tag                                                                 | Description                                                                                                                                               |
| ------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| app-entries                                                         | Desktop entry overrides from `hobbies_app_entry_overrides`, where `desktop_environment` is set                                                            |
| [betaflight](https://github.com/betaflight/betaflight-configurator) | FPV flight controller configurator                                                                                                                        |
| [expresslrs](https://github.com/ExpressLRS/ExpressLRS-Configurator) | ExpressLRS radio firmware flashing tool                                                                                                                   |
| fpv                                                                 | betaflight and expresslrs                                                                                                                                 |
| [freecad](https://www.freecad.org/)                                 | Parametric CAD                                                                                                                                            |
| [freerouting](https://github.com/freerouting/freerouting)           | PCB autorouter for KiCad; a subset of `kicad`                                                                                                             |
| [kicad](https://www.kicad.org/)                                     | Electronics schematic and PCB design, with [KiKit](https://github.com/yaqwsx/KiKit) and [kicad-jlcpcb-tools](https://github.com/Bouni/kicad-jlcpcb-tools) |
| [orcaslicer](https://github.com/OrcaSlicer/OrcaSlicer)              | 3D printer slicer (user flatpak)                                                                                                                          |

## Variables

See [defaults/main.yml](./defaults/main.yml).

| Variable                     | Purpose                                                                          |
| ---------------------------- | -------------------------------------------------------------------------------- |
| `hobbies_betaflight_version` | Pinned release; only raise it to one whose assets include `linux64-portable.zip` |
| `hobbies_kicad_version`      | Selects both the release PPA and the plugin directory                            |
| `hobbies_user`               | Account that user-scoped installs (flatpaks, KiCad plugins) apply to             |

## Notes

| Constraint            | Detail                                                                                                                                                 |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| betaflight is pinned  | Upstream ships only a PWA; the pinned release is the last with a Linux portable build                                                                  |
| freecad lags          | Installed from the maintainers' stable PPA (Ubuntu ships none), which lags the latest major release. `freecadcmd` runs FreeCAD Python scripts headless |
| freerouting analytics | `/usr/local/bin/freerouting` passes `-da` to disable them                                                                                              |
| Architectures         | freerouting and betaflight are x86_64 only; the role asserts a release exists for the host                                                             |
| Locked encrypted home | The role fails before any change when `hobbies_user`'s ecryptfs home is not mounted. Log in as that user or run `ecryptfs-mount-private`, then re-run  |
