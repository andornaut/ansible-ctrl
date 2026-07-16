#!/usr/bin/env python3
"""Generate RetroArch playlists (.lpl) from the ROM library.

RetroArch builds playlists with its in-app content scanner, which needs a display and must
be driven by hand on every host. Regenerating from the library instead keeps the ROM
directory -> core association in the games role (games_retroarch_systems).

Configured by RETROARCH_GENERATOR_CONFIG, a JSON document tasks/retroarch.yml puts in the
environment (games_retroarch_generator_config):

    {
      "library_dir":  "/path/to/rom-library",
      "playlist_dir": "~/.var/app/org.libretro.RetroArch/config/retroarch/playlists",
      "cores_dir":    "~/.var/app/org.libretro.RetroArch/config/retroarch/cores",
      "info_dir":     "~/.local/share/flatpak/.../share/libretro/info",
      "cores": {
        "gambatte": {"library_name": "Gambatte", "valid_extensions": ["gb", "gbc", "dmg"],
                     "block_extract": false}
      },
      "systems": {
        "Nintendo - Game Boy": {"core": "gambatte", "extensions": ["zip"]}
      }
    }

Optional keys let another host build playlists for a device it does not itself mount (the
Retroid sync, files/retroid/); absent, a same-host run is unchanged:

  * "core_filename_suffix" (default "_libretro.so"): the tail of a core's file
    ("_libretro_android.so" on Android), used to build core_path;
  * "emit_library_dir" (default = "library_dir"): the library root as the target sees it.
    The library is still scanned at "library_dir", but every path written into a playlist
    (each item's "path", and "scan_content_dir") has its "library_dir" prefix rewritten to
    this, so entries resolve on the device though the generator ran against another mount;
  * "emit_system_dirs" (default {}): per-system rename of the directory under emit_library_dir,
    for a target whose per-system folders are named differently. The Retroid's ES-DE tree uses
    short names ("snes") where the library uses No-Intro names ("Super Nintendo..."); a system
    absent from the map keeps its library name.

Two more keys give arcade systems readable labels (both host-agnostic, so the desktop sets them too):

  * "arcade_names_path" (default none): a JSON file mapping romset shortname -> full title
    (files/fbneo-arcade-names.json). A system whose core is in "arcade_name_cores" labels each
    file by its title ("Metal Slug - Super Vehicle-001") instead of its MAME id ("mslug"); the
    file on disk is untouched. Absent, every label stays the filename.
  * "arcade_name_cores" (default []): the cores that the map applies to (fbneo). Off this set the
    lookup never runs, so a console filename can never collide with a romset id.

"cores" is what the cores reported, collected by files/retroarch-probe-cores.py inside the
flatpak sandbox. Not gathered here: this runs on the host, where a core needing a library only
the runtime carries (LRPS2 wants libaio) will not load, leaving exactly those cores unchecked.

Owns the playlist directory, so it also:

  * validates every system against the core it names, exiting non-zero if a system declares
    content its core cannot launch (otherwise invisible until someone clicks a game and
    RetroArch segfaults);
  * writes a playlist only when its content would change, printing one line per rewrite so
    ansible's changed_when can key off stdout;
  * removes the playlists of systems that have left the table, but only ones it can prove it
    wrote (their scan_content_dir points inside the library); a hand-built playlist is not
    the role's to delete.

The library is only ever read, which lets a host mount it read-only.
"""

import functools
import json
import os
import sys

# Playlist fields RetroArch fills in when it scans, reproduced verbatim so a generated playlist
# is indistinguishable from a scanned one and RetroArch does not rewrite it on load.
# label_display_mode 3 hides the (Region) and [tag] suffixes in the UI while "label" keeps the
# full No-Intro name, which is what the thumbnail lookup matches on.
PLAYLIST_VERSION = "1.5"
LABEL_DISPLAY_MODE = 3
THUMBNAIL_MODE = 0
SORT_MODE = 0

# RetroArch stores a CRC as "<hex>|crc" and accepts an all-zero one, meaning "not computed".
# Hashing every ROM on a network-mounted library would cost minutes per run for a field only
# used for DAT matching, which this library does not rely on: it names files to No-Intro.
CRC32_UNKNOWN = "00000000|crc"


def accepted_extensions(info_dir, probed, core):
    """Return every extension a core will take, the union of two sources.

    The core's own valid_extensions (from the probe) is narrower and not what RetroArch enforces:
    content given as an explicit path is not filtered on extension at all, so Virtual Jaguar reports
    "j64|jag" yet loads this library's .rom files. The .info carries the superset RetroArch goes by.
    """
    declared = set(core_info_field(info_dir, core, "supported_extensions").split("|"))
    return (set(probed[core]["valid_extensions"]) | declared) - {""}


def validate_system(info_dir, probed, core, extensions):
    """Return the reasons a core cannot launch the extensions its system declares.

    Turns breakage that otherwise only shows when a human clicks a game into a failed run: a zip
    extension on a core that sets block_extract yet cannot open the archive itself segfaults
    RetroArch at load.
    """
    accepted = accepted_extensions(info_dir, probed, core)

    reasons = []
    for extension in extensions:
        # RetroArch matches on the final suffix, so Pico-8's compound "p8.png" is a "png" as
        # far as the core is concerned.
        effective = extension.rsplit(".", 1)[-1].lower()
        if effective == "zip":
            # RetroArch normally unpacks a .zip and hands the core what is inside. A core that sets
            # block_extract is handed the archive unopened: that breaks a core expecting the
            # extracted ROM (Dolphin), but is exactly what an arcade core wants, since its romset is
            # a multi-file .zip it opens itself and lists .zip among its own extensions. So reject
            # zip + block_extract only when the core does not itself accept .zip.
            if probed[core]["block_extract"] and "zip" not in accepted:
                reasons.append(
                    '"zip" is not launchable by %s: the core sets block_extract, so RetroArch '
                    "hands it the archive unopened" % core
                )
        elif effective not in accepted:
            reasons.append(
                '"%s" is not among the extensions %s accepts (%s)'
                % (extension, core, "|".join(sorted(accepted)))
            )
    return reasons


@functools.lru_cache(maxsize=None)
def core_info_field(info_dir, core, field, default=""):
    """Return one field from a core's .info file, or default when it is missing.

    Read from the .info rather than duplicated in the role's systems table, so it cannot drift from
    the installed core. Memoised because several systems share a core and would each reparse the file.
    """
    path = os.path.join(info_dir, "%s_libretro.info" % core)
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                key, _, value = line.partition("=")
                if key.strip() == field:
                    return value.strip().strip('"')
    except OSError:
        pass
    return default


def content_label(name, extensions):
    """Return a file's playlist label: its name with the system's extension taken off.

    Longest match wins, so Pico-8's compound "p8.png" is matched whole and "Celeste.p8.png" is
    labelled "Celeste" rather than "Celeste.p8". Returns None when the file is not launchable
    content for this system.
    """
    lowered = name.lower()
    for extension in sorted(extensions, key=len, reverse=True):
        suffix = "." + extension.lower()
        if lowered.endswith(suffix):
            return name[: -len(suffix)]
    return None


def disc_entry(directory, extensions):
    """Return the disc a visible subdirectory of a system directory should launch.

    Only 3DO uses these: its multi-disc games sit in a visible directory with no .m3u (Opera swaps
    discs itself), so the playlist points at disc 1. Every other system hides its multi-disc
    directory behind a dot prefix and exposes an .m3u; dot-prefixed directories never reach here.
    """
    discs = sorted(
        entry.path
        for entry in os.scandir(directory)
        if entry.is_file() and content_label(entry.name, extensions) is not None
    )
    if not discs:
        return None
    return next((disc for disc in discs if "(Disc 1)" in disc), discs[0])


def system_items(names, system_dir, emit_system_dir, extensions, core_path, core_name, db_name):
    """Build the playlist items for one system directory.

    Scanned at system_dir, but each item's path is written under emit_system_dir, which differs
    only when building for another host's mount (the Retroid sync). Equal, the rewrite is a no-op.

    names maps a romset shortname to its full title, for arcade systems whose files are named by
    MAME id (mslug.zip); empty for every other system, where the lookup is a no-op.
    """
    items = []
    for entry in sorted(os.scandir(system_dir), key=lambda e: e.name.lower()):
        # Dot-prefixed entries are the hidden per-game directories holding the discs of a
        # multi-disc game; the .m3u beside them is the launchable entry.
        if entry.name.startswith("."):
            continue

        if entry.is_dir():
            path = disc_entry(entry.path, extensions)
            label = entry.name
            if path is None:
                continue
        else:
            label = content_label(entry.name, extensions)
            if label is None:
                continue
            # Arcade romsets are named by short MAME id; show the full title as the label while the
            # path stays the romset file. The board-id suffix the title carries ("(NGM-2650)") is
            # hidden by label_display_mode 3, as "(USA)" is on a console. A no-op off arcade systems.
            label = names.get(label, label)
            # A .zip is listed by its own path, not "archive.zip#rom.sfc" as RetroArch's scanner
            # writes it: the frontend resolves a bare archive to the ROM inside on load either way,
            # and taking the path as-is means never opening archives across a network-mounted library.
            path = entry.path

        # Rewrite the scanned path onto the target's mount. path is always under system_dir.
        path = emit_system_dir + path[len(system_dir):]

        items.append(
            {
                "path": path,
                "label": label,
                "core_path": core_path,
                "core_name": core_name,
                "crc32": CRC32_UNKNOWN,
                "db_name": db_name,
            }
        )
    return items


def is_generated_playlist(path, library_dir):
    """Whether this .lpl is one this generator wrote, rather than one the user built.

    RetroArch's own playlists (Manual Scan, custom collections) land in the same directory with
    nothing in the filename to tell them apart, so ownership comes from the content: a playlist
    written here points scan_content_dir inside the ROM library, anything else does not.

    The answer decides whether a file is deleted, so every uncertainty resolves to "keep it".
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            playlist = json.load(handle)
    except (OSError, ValueError):
        return False
    if not isinstance(playlist, dict):
        return False

    scanned = playlist.get("scan_content_dir") or ""
    # commonpath raises rather than returning a mismatch when the paths are not both absolute,
    # so a relative scan_content_dir ("roms/snes", "~/roms") would otherwise take down a run
    # that merely walked past it.
    if not isinstance(scanned, str) or not os.path.isabs(scanned):
        return False
    return os.path.commonpath([scanned, library_dir]) == library_dir


def prune_playlists(playlist_dir, library_dir, systems):
    """Remove the generated playlists of systems that games_retroarch_systems no longer lists.

    Otherwise a dropped system leaves its .lpl behind while tasks/retroarch.yml deletes its core,
    so RetroArch goes on offering the system with every entry pointing at a missing core file.

    Only .lpl files directly in this directory, and only ones this generator wrote: RetroArch's own
    favourites and history live one level down in builtin/.
    """
    removed = []
    for name in sorted(os.listdir(playlist_dir)):
        path = os.path.join(playlist_dir, name)
        if not name.endswith(".lpl") or not os.path.isfile(path):
            continue
        if name[: -len(".lpl")] in systems:
            continue
        if not is_generated_playlist(path, library_dir):
            print("kept %s: not a generated playlist" % name, file=sys.stderr)
            continue
        os.remove(path)
        removed.append("removed %s" % name)
    return removed


def main():
    config = json.loads(os.environ["RETROARCH_GENERATOR_CONFIG"])

    library_dir = config["library_dir"]
    playlist_dir = config["playlist_dir"]
    cores_dir = config["cores_dir"]
    info_dir = config["info_dir"]
    probed = config["cores"]
    systems = sorted(config["systems"].items())
    # The library as the target sees it, and the core file's tail; both default to a same-host run.
    emit_library_dir = config.get("emit_library_dir", library_dir)
    emit_system_dirs = config.get("emit_system_dirs", {})
    core_suffix = config.get("core_filename_suffix", "_libretro.so")
    # Arcade romset -> full title map, applied only to systems whose core is listed in
    # arcade_name_cores (fbneo), whose files are named by short MAME id. Both absent by default, so
    # off arcade systems the lookup never happens and labels stay the filename.
    arcade_name_cores = set(config.get("arcade_name_cores", []))
    arcade_names = {}
    if config.get("arcade_names_path"):
        with open(config["arcade_names_path"], encoding="utf-8") as handle:
            arcade_names = json.load(handle)

    # An unmounted network share looks like an empty directory, and regenerating from that would
    # replace every playlist with an empty one.
    if not os.path.isdir(library_dir):
        sys.exit("%s: ROM library is not a directory" % library_dir)

    # The probe covers every installed core and the role installs every core the table names, so a
    # system naming a core that did not answer means the two disagree, not that the core is quiet.
    unknown = sorted({spec["core"] for _, spec in systems} - set(probed))
    if unknown:
        sys.exit("no installed core reported itself as: %s" % ", ".join(unknown))

    # Check the whole table before writing anything, reporting problems together: fixing them one
    # failed run at a time is worse.
    problems = [
        "%s: %s" % (system, reason)
        for system, spec in systems
        for reason in validate_system(info_dir, probed, spec["core"], spec["extensions"])
    ]
    if problems:
        sys.exit(
            "games_retroarch_systems declares content its cores cannot launch:\n  "
            + "\n  ".join(problems)
        )

    changed = []
    for system, spec in systems:
        system_dir = os.path.join(library_dir, system)
        if not os.path.isdir(system_dir):
            print("skipped %s: no such directory under the library" % system, file=sys.stderr)
            continue

        core = spec["core"]
        db_name = "%s.lpl" % system
        core_path = os.path.join(cores_dir, "%s%s" % (core, core_suffix))
        emit_system_dir = os.path.join(emit_library_dir, emit_system_dirs.get(system, system))
        # Falls back to the core's file name when the .info is missing, which costs only a
        # cosmetic label.
        core_name = core_info_field(info_dir, core, "display_name", default=core)
        names = arcade_names if core in arcade_name_cores else {}
        items = system_items(
            names, system_dir, emit_system_dir, spec["extensions"], core_path, core_name, db_name
        )

        # An existing playlist is never replaced by an empty one: a system directory that
        # scans to nothing means the extension list is wrong or the mount is half up, and
        # neither is worth discarding a good playlist over.
        if not items:
            print("skipped %s: no content matched %s" % (system, spec["extensions"]), file=sys.stderr)
            continue

        playlist = {
            "version": PLAYLIST_VERSION,
            "default_core_path": core_path,
            "default_core_name": core_name,
            "base_content_directory": "",
            "label_display_mode": LABEL_DISPLAY_MODE,
            "right_thumbnail_mode": THUMBNAIL_MODE,
            "left_thumbnail_mode": THUMBNAIL_MODE,
            "thumbnail_match_mode": THUMBNAIL_MODE,
            "sort_mode": SORT_MODE,
            # Set so that RetroArch's in-app "Refresh Playlist" rescans the right directory, and it
            # is the marker prune_playlists proves ownership by, so it takes the target's mount.
            "scan_content_dir": emit_system_dir,
            "scan_file_exts": "",
            "scan_dat_file_path": "",
            "scan_search_recursively": True,
            "scan_search_archives": True,
            "scan_filter_dat_content": False,
            "scan_overwrite_playlist": True,
            "items": items,
        }
        content = (json.dumps(playlist, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

        # Compared as bytes, not text: a playlist RetroArch scanned itself is not necessarily
        # valid UTF-8, and decoding one to test whether it is already current would fail before
        # it could be replaced.
        path = os.path.join(playlist_dir, db_name)
        try:
            with open(path, "rb") as handle:
                if handle.read() == content:
                    continue
        except OSError:
            pass

        with open(path, "wb") as handle:
            handle.write(content)
        changed.append("%s (%d)" % (system, len(items)))

    changed.extend(prune_playlists(playlist_dir, emit_library_dir, config["systems"]))

    for entry in changed:
        print(entry)


if __name__ == "__main__":
    main()
