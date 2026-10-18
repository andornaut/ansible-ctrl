# Helper scripts

The role runs these from `../tasks/retroarch.yml` and `../tasks/lutris.yml`. Each can be run by hand to debug a
single stage. Each script's module docstring is the reference for its input and edge cases.

| Script                            | Purpose                                                                                          | Input                                                                         |
| --------------------------------- | ------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------- |
| `retroarch-probe-cores.py`        | Reports each installed core's `library_name` and extensions as JSON                              | Cores directory                                                               |
| `retroarch-generate-playlists.py` | Regenerates the `.lpl` playlists from the ROM library                                            | `RETROARCH_GENERATOR_CONFIG`                                                  |
| `retroarch-fetch-thumbnails.py`   | Fills the shared thumbnail cache from [thumbnails.libretro.com](https://thumbnails.libretro.com) | `RETROARCH_THUMBNAILS_CONFIG`                                                 |
| `gen-fbneo-arcade-names.py`       | Regenerates the committed `fbneo-arcade-names.json`. Run by hand when fbneo adds games           | None. Needs network access                                                    |
| `3ds-intake.py`                   | Checks a 3DS image against No-Intro, and decrypts a card image or CIA into a `.3ds`. Run by hand | An image. Decryption reads `~/.3ds/aes_keys.txt`, and `seeddb.bin` beside it  |
| `lutris-game-prefix.py`           | Prints a Lutris game's wine prefix                                                               | `LUTRIS_PREFIX_CONFIG`                                                        |
| `lutris-register-game.py`         | Registers a Lutris game derived from another game's configuration                                | `LUTRIS_REGISTER_CONFIG`                                                      |
| `lutris-unset-game-env.py`        | Removes environment variables from each Lutris game's own `system.env`                           | `LUTRIS_UNSET_ENV_CONFIG`                                                     |
| `lutris-launch-game.py`           | Clears a stale wine prefix, then launches the Lutris game                                        | Wine prefix, flatpak application ID, Lutris slug and an optional display name |
| `wow-install-addons.py`           | Installs each World of Warcraft addon's newest Wago release into every game version directory    | `WOW_ADDONS_CONFIG`                                                           |

| Constraint                | Detail                                                                                                                                                            |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Runtime order             | probe, then generate, then fetch                                                                                                                                  |
| Writes to the ROM library | Only the thumbnail fetcher. Run it on the host whose mount is writable                                                                                            |
| Run inside the sandbox    | The probe and the three Lutris config scripts run inside their flatpak with `flatpak run --command=python3`. The launcher and the addon installer run on the host |

## RetroArch

Paths are those of a `--user` flatpak install. The generator and fetcher exit non-zero on a problem they detect.

```bash
config="$HOME/.var/app/org.libretro.RetroArch/config/retroarch"
info="$HOME/.local/share/flatpak/app/org.libretro.RetroArch/current/active/files/share/libretro/info"

# Probe the cores
cores=$(flatpak run --command=python3 org.libretro.RetroArch - "$config/cores" < retroarch-probe-cores.py)

# Regenerate the playlists
RETROARCH_GENERATOR_CONFIG=$(cat <<JSON
{
  "library_dir": "/media/nas/games",
  "playlist_dir": "$config/playlists",
  "cores_dir": "$config/cores",
  "info_dir": "$info",
  "cores": $cores,
  "systems": {"Nintendo - Game Boy": {"core": "gambatte", "extensions": ["zip"]}}
}
JSON
) ./retroarch-generate-playlists.py

# Fill the thumbnail cache
RETROARCH_THUMBNAILS_CONFIG=$(cat <<JSON
{"playlist_dir": "$config/playlists", "thumbnails_dir": "/media/nas/games/_Thumbnails"}
JSON
) ./retroarch-fetch-thumbnails.py
```

## Lutris

```bash
lutris=$HOME/.var/app/net.lutris.Lutris/data/lutris

LUTRIS_PREFIX_CONFIG='{"config_dir": "'"$lutris"'", "data_dir": "'"$lutris"'", "slug": "battlenet"}' \
  flatpak run --command=python3 net.lutris.Lutris - < lutris-game-prefix.py

LUTRIS_REGISTER_CONFIG='{"config_dir": "'"$lutris"'", "data_dir": "'"$lutris"'",
  "source_slug": "battlenet", "slug": "world-of-warcraft", "name": "World of Warcraft",
  "game": {"args": "--exec=\"launch WoW\""}}' \
  flatpak run --command=python3 net.lutris.Lutris - < lutris-register-game.py

./lutris-launch-game.py "$HOME/.local/games/Lutris/battlenet" net.lutris.Lutris world-of-warcraft
```

## 3DS intake

The azahar core loads only decrypted `.3ds` images. Verify the decrypted image: the No-Intro card DAT hashes
decrypted, untrimmed images.

| Constraint         | Detail                                                                                                                                        |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Keys               | A Citra-format `aes_keys.txt` dumped from a console, at `~/.3ds/aes_keys.txt` or `--keys`. Read only for an encrypted source. Never committed |
| Seeds              | A digital title whose NCCH uses a seed also needs `seeddb.bin`, at `~/.3ds/seeddb.bin` or `--seeddb`                                          |
| Output             | Every partition decrypted and its hashes checked, so a wrong key fails the run. The card's full size is kept, padding included                |
| CIA                | Contents become the partitions of the same index. An update or DLC CIA, which holds no content 0, is refused                                  |
| An encrypted image | Never matches the card DAT. Decrypt it, then verify the result                                                                                |

```bash
./3ds-intake.py verify "Game (USA).3ds"
./3ds-intake.py decrypt "Game (USA).3ds" "/media/nas/games/Nintendo - Nintendo 3DS/Game (USA).3ds"
./3ds-intake.py decrypt "Game (USA) (eShop).cia" "/media/nas/games/Nintendo - Nintendo 3DS/Game (USA) (eShop).3ds"
```
