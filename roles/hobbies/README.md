# ansible-role-hobbies

Installs 3D printing, electronics, and FPV tools on Ubuntu.

## Usage

```bash
make hobbies
make hobbies -- --tags kicad
```

## Tags

| Tag                                                                 | Description                                                                                                                                                                                                                                                                                                       |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| app-entries                                                         | Desktop entry overrides for the applications this role installs, from `hobbies_app_entry_overrides`: copies in `~/.local/share/applications` that hide an entry or set its categories, pruned when unnamed. Only where `desktop_environment` is set. Same mechanism as the [desktop](../desktop/README.md) role's |
| [betaflight](https://github.com/betaflight/betaflight-configurator) | FPV flight controller configurator                                                                                                                                                                                                                                                                                |
| [expresslrs](https://github.com/ExpressLRS/ExpressLRS-Configurator) | ExpressLRS radio firmware flashing tool                                                                                                                                                                                                                                                                           |
| fpv                                                                 | betaflight and expresslrs                                                                                                                                                                                                                                                                                         |
| [freecad](https://www.freecad.org/)                                 | Parametric CAD for modelling parts around PCBs                                                                                                                                                                                                                                                                    |
| [freerouting](https://github.com/freerouting/freerouting)           | PCB autorouter for KiCad; a subset of `kicad`                                                                                                                                                                                                                                                                     |
| [kicad](https://www.kicad.org/)                                     | Electronics schematic and PCB design, with plugins                                                                                                                                                                                                                                                                |
| [orcaslicer](https://github.com/OrcaSlicer/OrcaSlicer)              | 3D printer slicer (user flatpak)                                                                                                                                                                                                                                                                                  |

## Variables

See [defaults/main.yml](./defaults/main.yml).

| Variable                     | Purpose                                                                          |
| ---------------------------- | -------------------------------------------------------------------------------- |
| `hobbies_betaflight_version` | Pinned release; only raise it to one whose assets include `linux64-portable.zip` |
| `hobbies_kicad_version`      | Selects both the release PPA and the plugin directory                            |
| `hobbies_user`               | Account that user-scoped installs (flatpaks, KiCad plugins) apply to             |

## Installed files

| Path                                                                          | Purpose                                                                                                                 |
| ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `/opt/betaflight/<version>`                                                   | betaflight release; `/opt/betaflight/current` links to the application directory in it                                  |
| `/usr/local/bin/betaflight-configurator`                                      | betaflight launcher on PATH                                                                                             |
| `/opt/freerouting/<version>`                                                  | freerouting release; `/opt/freerouting/current` links to it                                                             |
| `/usr/local/bin/freerouting`                                                  | Wrapper that passes `-da` to disable analytics                                                                          |
| `/usr/local/share/applications/{betaflight-configurator,freerouting}.desktop` | Menu entries, under `/usr/local` because `/usr/share/applications` is dpkg's                                            |
| `/etc/apt/sources.list.d/`                                                    | The `kicad/kicad-<version>-releases` and `freecad-maintainers/freecad-stable` PPAs                                      |
| `/opt/kikit`                                                                  | [KiKit](https://github.com/yaqwsx/KiKit) venv for panelization                                                          |
| `~/.local/share/kicad/<version>/scripting/plugins/kicad-jlcpcb-tools`         | [kicad-jlcpcb-tools](https://github.com/Bouni/kicad-jlcpcb-tools) plugin for LCSC part lookup, in `hobbies_user`'s home |

## Notes

| Constraint            | Detail                                                                                                                                                                                                                                                                                              |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| betaflight is pinned  | Upstream ships only a PWA; the pinned release is the last with a Linux portable build                                                                                                                                                                                                               |
| freecad source        | The maintainers' stable PPA; Ubuntu ships no freecad package. That series lags the latest major release                                                                                                                                                                                             |
| `freecadcmd`          | Runs FreeCAD Python scripts headless. From `freecad-python3`, linked against the archive's OpenCascade (`libocct-*`)                                                                                                                                                                                |
| kicad source          | The release PPA that `hobbies_kicad_version` selects                                                                                                                                                                                                                                                |
| KiKit from git master | Its PyPI releases lag the KiCad version the PPA installs                                                                                                                                                                                                                                            |
| Release architectures | Freerouting publishes a `linux-x64` build only, and the role asserts one exists for the host. ExpressLRS takes the `.deb` named for the Debian architecture in `hobbies_arch`                                                                                                                       |
| Locked encrypted home | The role fails before any change when `hobbies_user`'s home is encrypted (`<home's parent>/.ecryptfs/<user>` exists) and not mounted. Log in as that user or run `ecryptfs-mount-private`, then re-run. A marker left by an account whose home is no longer encrypted fails the same way; remove it |
