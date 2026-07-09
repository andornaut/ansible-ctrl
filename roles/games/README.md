# ansible-role-games

Installs gaming Apt packages and Flatpaks on Ubuntu.

## Requirements

None. The role installs `flatpak` and adds the flathub remote for `games_user` itself, so
it runs standalone on a host that has never had the [desktop](../desktop/) role applied.
Hosts in the `games` group are normally also in `desktop`, but that is an inventory
convention, not a role dependency: pulling desktop in via `meta/main.yml` would make
`make games` purge snapd, rewrite GRUB, and install a display manager and browsers.

## Usage

```bash
make games

# Or run a subset by tag
ansible-playbook --ask-become-pass games.yml --tags flatpak
```

## Variables

See [defaults/main.yml](./defaults/main.yml).

| Variable | Default | Purpose |
| --- | --- | --- |
| `games_user` | remote user | Account that flatpaks are installed for (`--user`, never root) |
| `games_gamescope_apt_available` | Ubuntu >= 26.04 | Platform probe: whether the `gamescope` apt package exists for native games |
| `games_flatpak_apps` | see defaults | Flatpak applications to install |
| `games_flatpak_runtime_branch` | `25.08` | `org.freedesktop.Platform` branch the Vulkan layers are pinned to |
| `games_flatpak_extensions` | MangoHud, gamescope | Vulkan layers installed into flatpak, pinned to the runtime branch |
| `games_flatpak_overrides` | cursor theme, Steam PipeWire | `flatpak override --user` arguments per application ID; the `default` key applies to every app |

Set `games_user` per host in `host_vars/` when the gaming account differs from the account
running the play.

Ansible replaces dict variables rather than merging them, so a `host_vars/` override of
`games_flatpak_overrides` must restate the `default` key. Omitting it fails the play,
because `flatpak.yml` dereferences `default` unguarded.
