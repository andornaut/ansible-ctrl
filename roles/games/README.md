# ansible-role-games

Installs gaming apt packages and flatpaks on Ubuntu, and configures RetroArch against the ROM library.

## Usage

```bash
make games
make games -- --tags flatpak
make games -- --tags retroarch
```

## Tags

| Tag | Description |
| --- | --- |
| apt | Native gaming packages |
| flatpak | Flatpak runtime, flathub remote, applications, extensions, and overrides |
| heroic | Heroic install path and the store token-refresh timer |
| lutris | Lutris default install path |
| retroarch | Libretro cores, BIOS, settings, per-core overrides, playlists, and thumbnails |

## Variables

See [defaults/main.yml](./defaults/main.yml).

| Variable | Purpose |
| --- | --- |
| `games_user` | Account flatpaks are installed for (`--user`, never root). Set in `host_vars/` when it differs from the play's account |
| `games_flatpak_apps` | Flatpak applications to install |
| `games_flatpak_runtime_branch` | `org.freedesktop.Platform` branch the Vulkan layers are pinned to |
| `games_flatpak_overrides` | `flatpak override --user` arguments per application ID; the `default` key applies to every app |
| `games_heroic_dir` | Heroic's game installs and wine prefixes: granted to its sandbox, and written into its `config.json` |
| `games_heroic_token_refresh_interval` | How often the `--user` timer exercises the Epic and GOG OAuth refresh tokens |
| `games_lutris_dir` | Lutris's game installs, written into its `system.yml` |
| `games_retroarch_library_dir` | ROM library. No default: set in `host_vars/`. The role reads it and writes nothing but the thumbnail cache |
| `games_retroarch_controller` | The gamepad this host has, naming a key of `games_retroarch_controllers`. No default: set in `host_vars/` |
| `games_retroarch_video_refresh_rate` | This host's panel refresh rate, folded into the settings as `video_refresh_rate`. No default: set in `host_vars/` |
| `games_retroarch_bios_dir` | BIOS set, copied into RetroArch's system directory |
| `games_retroarch_thumbnails_dir` | Shared box art / title / snap cache for the playlist browser |
| `games_retroarch_systems` | Library subdirectory to core and launchable extensions |
| `games_retroarch_required_settings` | The `retroarch.cfg` keys the role owns |
| `games_retroarch_extra_settings` | Per-host additions, merged over the required settings |
| `games_retroarch_core_overrides` | Per-core `retroarch.cfg` overrides, keyed by the buildbot core name |
| `games_retroarch_core_options` | Per-core *core options* (the core's own settings), keyed by the same core name |

[vars/main.yml](./vars/main.yml) holds fact-derived values, among them `games_gamescope_apt_available` (whether the
apt package exists on this release) and `games_flatpak_extensions` (the MangoHud and gamescope Vulkan layers). Role
vars outrank `host_vars`, so override the default they derive from, not the derived value.

## Notes

- The role has no dependencies: it installs `flatpak` and adds the flathub remote for `games_user` itself, so it
  runs standalone on a host that has never had the [desktop](../desktop/) role applied.
- Ansible replaces dict variables rather than merging them, so a `host_vars/` override of
  `games_flatpak_overrides` must restate the `default` key; `flatpak.yml` dereferences it unguarded. Prefer
  `games_retroarch_extra_settings` for RetroArch tweaks, which is combined with the required settings key by key.

## RetroArch

**Close RetroArch before running the play.** It rewrites `retroarch.cfg` and its core options on exit
(`config_save_on_exit`), so a running instance overwrites whatever the play enforced. The `retroarch` tag asserts it
is not running.

Everything RetroArch owns lives under `~/.var/app/org.libretro.RetroArch/config/retroarch`, except the thumbnail
cache, which is shared through the library (see [Thumbnails](#thumbnails)). Keeping every writable path (playlists,
saves, states, `system/`, cache) under the per-user directory is what lets a host mount the library read-only over
the network.

`retroarch.cfg` holds thousands of keys; the role owns only those in `games_retroarch_required_settings`. Settings
changed in the app still persist, and the managed keys snap back on the next run.

### Per-host settings

Three values have no default and are asserted by the play. Each is site data or hardware the role cannot see, where
a guessed value would fail silently.

| Setting | Why |
| --- | --- |
| `games_retroarch_library_dir` | Where the host mounts the ROM library. Site data, and this repo is public. The tag also asserts the library is mounted. |
| `games_retroarch_controller` | Which pad is plugged in. See [Controller bindings](#controller-bindings). |
| `games_retroarch_video_refresh_rate` | The panel's actual mode. RetroArch derives the audio resampling ratio from it, so the 60.0 default mistimes every core on a high-refresh panel, heard as drift. "Estimate Screen Refresh Rate" in the menu reports it. |

`vrr_runloop_enable` is optional: turn it on in `games_retroarch_extra_settings` for a VRR panel, which also wants
VRR enabled outside RetroArch (a compositor setting under Wayland; `Option "VariableRefresh"` in `xorg.conf.d` under
X11, where it conflicts with `TearFree`). It cannot be combined with the other video-to-audio sync methods (vsync, a
swap interval above 1, black frame insertion), and the play asserts those preconditions. On a fixed-refresh panel
leave it off and use BFI instead.

### Input devices

`input_driver` is `udev`, not `x`: the games hosts run both X11 and Wayland sessions, and the `x` driver only works
under an X11 video context. RetroArch then reads `/dev/input/event*` directly and needs read access to those
devices. The distro's `70-uaccess.rules` tags joysticks for `uaccess` but not the mouse or keyboard, so out of the
box the gamepad works while the pointer (menu) and lightgun are dead.

[files/70-retroarch-input.rules](./files/70-retroarch-input.rules) tags the mouse and keyboard too; logind turns the
tag into an ACL for whoever holds the active seat and drops it at logout, the same mechanism `steam-devices` uses
for pads. The trade is that any process in the seat's session can then read raw keystrokes from every keyboard.
Under X11 this changes nothing (any X client can already snoop the keyboard); under Wayland it is a real reduction
in isolation, accepted here because these are single-user gaming hosts. Adding the user to the `input` group (the
alternative in RetroArch's docs) is worse: a standing grant covering every session including SSH, not the seat
alone.

The same rules file also drops the mouse classification (`ID_INPUT_MOUSE`) of one device, an idle KVM / virtual-HID
(USB id `09eb:0131`). RetroArch reads menu clicks and the lightgun from the mouse at `input_player1_mouse_index`, and
selects it by position in a list built in device-enumeration order, not by a stable name. A virtual HID that
advertises buttons but emits nothing takes a slot in that list, and if it sorts first it becomes index 0, the
default: the cursor still moves (motion is aggregated across all mice) while every click lands on the dead device.
Setting the index by hand does not fix it, the order not being stable across launches; removing the phantom from the
mouse pool does, leaving a real mouse at index 0. The rule matches that one USB id, so it is a no-op on a host
without the device; a host with a different idle virtual mouse adds its own id.

### Playlists

RetroArch's in-app scanner needs a display and must be driven by hand on every host.
[files/retroarch-generate-playlists.py](./files/retroarch-generate-playlists.py) regenerates the `.lpl` files from
the library instead, so the ROM directory to core association lives in `games_retroarch_systems`. Adding a ROM means
re-running the `retroarch` tag.

- **Multi-disc games** follow the library's own `AGENTS.md`: the discs sit in a dot-prefixed directory the generator
  skips, and the `.m3u` beside it is the launchable entry. The 3DO and GameCube are the exceptions (a visible
  directory and no `.m3u`, because Opera and Dolphin swap discs themselves). The table below maps each system to
  its layout.
- **The generator owns the playlist directory.** A `.lpl` whose system has left `games_retroarch_systems` is
  deleted, so it cannot keep being offered after the core prune removes the core it points at. Only `.lpl` files
  directly in the directory and written by the generator are touched: RetroArch's favourites and history live in
  `builtin/`, and hand-built playlists are not the role's to delete.
- **An existing playlist is never replaced by an empty one**, and the play asserts the library is mounted first: an
  unmounted network share otherwise looks exactly like an empty library.
- **`games_retroarch_systems` is validated against the cores** before anything is written; a system declaring
  content its core cannot launch fails the play (e.g. a `zip` extension on Dolphin, which sets `block_extract` and
  is handed the archive unopened).

Which layout a system uses is decided by whether its core reads an `.m3u`: the cores that do get a hidden folder
and an `.m3u` (only the `.m3u` is offered and disc-swap is automatic); the cores that do not get a visible folder
and no `.m3u`. All discs of a game share one container format (all `.chd`, or all `.rvz` on GameCube).

| System | Core | Multi-disc layout |
| --- | --- | --- |
| PlayStation | Beetle PSX HW | hidden `.Game/` + `.m3u`, `.chd` |
| PlayStation 2 | LRPS2 | hidden `.Game/` + `.m3u`, `.chd` |
| Saturn | Beetle Saturn | hidden `.Game/` + `.m3u`, `.chd` |
| Dreamcast | Flycast | hidden `.Game/` + `.m3u`, `.chd` |
| Mega-CD / Sega CD | Genesis Plus GX | hidden `.Game/` + `.m3u`, `.chd` |
| TurboGrafx-CD | Beetle PCE | hidden `.Game/` + `.m3u`, `.chd` |
| 3DO | Opera | visible `Game/`, no `.m3u`, `.chd` |
| GameCube | Dolphin | visible `Game/`, no `.m3u`, `.rvz` |
| PSP | PPSSPP | single-UMD, no multi-disc |
| Cartridge systems | (various) | single file, no multi-disc |

A `.zip` is listed by its own path, not as `archive.zip#rom.sfc`: RetroArch resolves the archive on load, so the
generator never opens every archive across a network mount.

### Cores

Libretro cores are not packaged for apt or flatpak; RetroArch's in-app Core Updater fetches them from the libretro
buildbot one at a time. This role installs them from the same source declaratively and owns the cores directory:

- **Every run installs the current build.** The buildbot ships nightlies only, so there is no release to pin and no
  in-place upgrade. This is also what repairs a core the flatpak runtime can no longer load after a runtime upgrade:
  the replacement is built against the current runtime.
- **Cores no system is associated with are removed**, so a superseded core cannot linger in "Load Core" and invite a
  game onto the wrong one.

The download is `get_url` into `~/.cache/libretro-cores`, extracted only when the archive changed. The buildbot
never answers `304`, so the archives are fetched every run either way, but `get_url` compares fetched against
on-disk, so a run reports a core changed only when a binary really moved. Letting `unarchive` download instead
re-extracts everything every run and reports everything changed, making "the cores changed" meaningless.

Each core is then dlopened **inside the sandbox** to read its reported name (see
[Per-core overrides](#per-core-overrides-and-core-options)), which doubles as the load check: freshly refetched, a
core that still will not load is a broken build, and the play names it and stops. The core set is the desktop (x64)
column of the [til notes](https://github.com/andornaut/til/blob/main/docs/retro-games.md#cores).

**Swapping a core orphans that system's saves.** RetroArch sorts saves and states into per-core directories
(`saves/<library_name>/`, `states/<library_name>/`). Save states cannot migrate (a dump of the old core's internal
state); battery saves usually can, but only within an emulator family (Mednafen's `.srm` moves between its cores;
DeSmuME's `.dsv` is not a melonDS `.sav`). Move battery saves by hand and delete the states.

### BIOS

The BIOS set is copied out of the library into RetroArch's `system/` directory rather than pointed at in place:
cores treat that directory as writable scratch (Dolphin's `Sys` tree, PPSSPP's state), so it must be local and would
not be writable on a read-only network mount anyway.

The copy is `rsync`, not `ansible.builtin.copy`: the set runs to thousands of files and `copy` checksums every one
on every run, which over the network means reading the whole set back each time; `rsync` compares size and mtime. It
runs without `--delete`, because the cores' own state lives in that directory alongside the BIOS.

### Thumbnails

RetroArch downloads box art, title screens, and snaps from `thumbnails.libretro.com` on demand as games are scrolled
past. Left at its default the cache lands per-user, so every host re-downloads the same images.
`thumbnails_directory` instead points at `games_retroarch_thumbnails_dir` in the library, the one thing RetroArch
writes that hosts can share: a thumbnail is looked up by playlist *label*, and the playlists are generated from that
same library, so a cache one host fills is valid on all of them.

- **Only the host whose mount is writable downloads into it.** `network_on_demand_thumbnails` is derived per host
  from a stat of the directory: on a read-only mount it is turned off, or RetroArch retries an unsaveable download
  every time a game is scrolled past. Those hosts read the cache; the writer fills it.
- **The library owns the directory, not this role**, as it owns the BIOS set: the play points RetroArch at it and
  never creates it. The playlist generator only looks inside the system directories `games_retroarch_systems` names.
- **It must be setgid and in the library's group**: the share only serves what is group-readable in that group, and
  the per-playlist directories RetroArch creates inherit the group from it. This is the library's own setup to get
  right, not the play's to police (it checks only that the cache exists): a network client is served ownership and
  mode the protocol invents (CIFS: `uid=0`, `gid=0`, `dir_mode=0755`), so there is no reliable way to validate the
  real bits from most hosts anyway.
- **Nothing else RetroArch writes may move here.** Saves, states, `system/`, and the cache are written on every
  launch and a read-only mount would break them. The achievement badge cache (`cheevos/`) is also per-user, so
  badges do not cache on a read-only host.

[files/retroarch-fetch-thumbnails.py](./files/retroarch-fetch-thumbnails.py) fills the cache for every game in the
generated playlists, on the writable host, right after the playlists are written. On-demand downloading only fetches
what is scrolled past, so a game never browsed would have no thumbnail anywhere; the play keeps the cache complete.

A thumbnail is looked up by playlist label, and both the library and the thumbnail repository name games to the
**No-Intro standard**, so the ordinary case is an exact match. The script names a mismatch on stderr. Two cases
resolve beyond an exact match:

- **A dump the repository has never heard of** (translation, fix, homebrew): its `(Region)`/`(Tag)` suffixes match
  no release, but the base game does. Matched on the bare title, and only when exactly one release answers to it, so
  two regional dumps never get each other's art.
- **A Pico-8 cart**, which is already a picture of itself: the `.p8.png` *is* the label art, and the repository
  carries no Pico-8 art. The script copies the cart.

Names resolve against the repository's directory listing rather than a guess, costing one request per system that
still has a gap (a converged host makes none). A game the repository does not carry keeps its system re-listed every
run, so art added upstream later is picked up; such games otherwise want art supplied by hand.

### Per-core overrides and core options

Both are keyed by the buildbot core name, as `games_retroarch_systems` is (`dolphin`, `pcsx2`). RetroArch looks the
files up under `config/<library_name>/`, where `library_name` is what the built core reports at runtime, a third
name for the same core (the GameCube core is `dolphin` on the buildbot, `Dolphin` in its `.info`, and reports
`dolphin-emu`).

`library_name` is a property of the build, not the core, which is why it is not written down in this role: the PS2
core's reported name varies across nightlies (`LRPS2 (alpha)` vs `LRPS2`), so hosts on different builds want
different directories. A hardcoded name would be right on one and silently wrong on the other, so the play asks the
cores.
[files/retroarch-probe-cores.py](./files/retroarch-probe-cores.py) dlopens each core **inside the flatpak sandbox**
(the only place they all load: LRPS2 needs `libaio`, which only the runtime carries) and reports each core's
`library_name`, `valid_extensions`, and `block_extract`. The playlist generator, which runs on the host, is handed
that answer rather than probing again.

Override and option keys are asserted against `games_retroarch_systems`, so an override for a core no system runs
fails the play. A core that renames itself across an upgrade orphans its old files, and the prune removes them.

| | File | Written | Why |
| --- | --- | --- | --- |
| `games_retroarch_core_overrides` | `config/<library_name>/<library_name>.cfg` | whole, from a template | An override file holds only the keys that differ from the global config, so there is nothing else to preserve |
| `games_retroarch_core_options` | `config/<library_name>/<library_name>.opt` | key by key | RetroArch writes *every* option a core exposes into this file, so writing it whole would discard every option the role has no opinion on |

The overrides carry the exceptions to four global settings:

- **Video driver.** Beetle PSX HW, Flycast, and Mupen64Plus-Next run on `vulkan` while the global stays `glcore`. A
  `vulkan` global would drag PPSSPP and Dolphin onto their Vulkan backends too, which is where their bugs are.
- **Rewind**, on globally and wherever the core can take it. Only Dolphin, LRPS2, and Virtual Jaguar turn it off,
  because RetroArch refuses rewind for a `basic` core (the first two) or one declaring no savestates (the third).
  `rewind_buffer_size` is raised from RetroArch's handheld-sized 20MB default to 256MB.
- **Preemptive frames**, the other way round: off globally, on per core. RetroArch permits them only on a
  `deterministic` core and nags on screen otherwise, so the overrides name the cheap deterministic cores. Beetle PSX
  HW and Beetle Saturn qualify but are left out, being too expensive to re-run a frame on every input change.
- **The right-stick axes**, unbound on the dual-analog consoles (see below).

Whether a core can rewind or take preemptive frames comes from the same `.info` field:

```bash
grep savestate_features <info_dir>/*_libretro.info
```

#### Controller bindings

Rewind and fast-forward are bound three ways so every core can reach them:

| Binding | Where | Notes |
| --- | --- | --- |
| Right analog stick (up / down) | every core whose console has no right stick | the primary |
| L3 / R3 | everywhere except the PS2 | no console here has clickable sticks, so they are free; PS2 games use them, so it takes them back |
| Keyboard `r` / `l` | every core, always | never taken away |

The dual-analog consoles (PlayStation, GameCube, PS2) unbind the stick, or looking around would scrub the game. A
Hotkey-Enable combo is deliberately not used: it gates *every* hotkey, so binding it would mean holding Select to
use the right stick too.

**The gamepad bindings are per-controller, from `games_retroarch_controller` in `host_vars/`.** RetroArch's
`input_*_btn` and `input_*_axis` are *physical* device indices, not RetroPad IDs, and differ per pad. There is no
portable value, so the role has no default and asserts the variable; a wrong value binds a different button rather
than no-oping. Read the real indices from RetroArch's autoconfig profile for the pad
and add an entry to `games_retroarch_controllers`:

```bash
flatpak run --command=grep org.libretro.RetroArch -E '^input_(r_y_minus_axis|r_y_plus_axis|l3_btn|r3_btn)' \
  "/app/share/libretro/autoconfig/udev/Microsoft_X-Box_Series_XS_pad.cfg"
```

#### Core options

Core options are the core's own settings, namespaced per core and not discoverable from `retroarch.cfg`. Read the
real ones out of the `.so` (the libretro docs lag the cores):

```bash
strings <cores_dir>/genesis_plus_gx_libretro.so | grep '^genesis_plus_gx_'
```

Both cores configured this way trade CPU for accuracy: Nuked FM synthesis on Genesis Plus GX, and ParaLLEl-RDP/RSP
on Mupen64Plus-Next. ParaLLEl is Vulkan-only and the core requests a Vulkan context only when its `rdp-plugin`
option is `parallel`, so the core option and the `video_driver` override must be set together or it silently does
not engage.

### Handheld sync (Retroid Pocket Flip 2)

[files/retroid/](./files/retroid/) mirrors this same managed config onto a Retroid Pocket Flip 2 (Snapdragon 865,
stock Android + ES-DE), which Ansible cannot reach. `sync.py` reads this role's `defaults/main.yml` as the source of
truth, applies the Android divergences in `files/retroid/profile.yml` (ARM cores from the Android buildbot, Android
drivers and directories, the Saturn/N64/GameCube/PS2 core changes), and reconciles the result onto the device over
`adb` with the role's own ownership semantics (own the named keys, prune the dropped cores and playlists). It reuses
`retroarch-generate-playlists.py` unchanged via its `core_filename_suffix`/`emit_library_dir` config keys. Not wired
into any playbook; run by hand. See [files/retroid/README.md](./files/retroid/README.md).
