#!/usr/bin/env python3
"""Generate RetroArch playlists (.lpl) from the ROM library.

Replaces RetroArch's in-app scanner, which needs a display and a human on every host, and
keeps the ROM directory -> core association in games_retroarch_systems.

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

Optional keys let one host build playlists for a device it does not mount (the Retroid sync,
files/retroid/); absent, a same-host run is unchanged:

  * "core_filename_suffix" (default "_libretro.so"): tail of a core's file, used to build
    core_path ("_libretro_android.so" on Android);
  * "emit_library_dir" (default = "library_dir"): library root as the target sees it. Scanning
    still happens at "library_dir", but every emitted path has that prefix rewritten to this;
  * "emit_system_dirs" (default {}): per-system rename of the directory under emit_library_dir,
    for a target naming its folders differently (ES-DE's "snes" vs No-Intro). Unlisted systems
    keep their library name.

Two host-agnostic keys give arcade systems readable labels:

  * "arcade_names_path" (default none): JSON mapping romset shortname -> full title
    (files/fbneo-arcade-names.json);
  * "arcade_name_cores" (default []): cores the map applies to (fbneo). Off this set labels
    stay the filename, so a console filename cannot collide with a romset id.

A system may carry "game_cores", mapping a playlist label to the core one title needs instead of
the system's own -- a Sega CD disc that also needs the 32X stays a Sega CD game everywhere except
core_path. Validated like a system, and a label matching no content is an error.

"cores" is what the cores reported, collected by files/retroarch-probe-cores.py inside the flatpak
sandbox. Not gathered here: a core needing a runtime-only library (LRPS2 wants libaio) will not
load on the host, leaving exactly those cores unchecked.

Run-time behaviour and the read-only-library property are in files/README.md.
"""

import functools
import json
import os
import sys

# Reproduced verbatim from what RetroArch writes when it scans, so it does not rewrite a generated
# playlist on load. label_display_mode 3 hides the (Region) and [tag] suffixes in the UI while
# "label" keeps the full No-Intro name, which is what the thumbnail lookup matches on.
PLAYLIST_VERSION = "1.5"
LABEL_DISPLAY_MODE = 3
THUMBNAIL_MODE = 0
SORT_MODE = 0

# All-zero means "not computed", which RetroArch accepts. The field is only used for DAT matching;
# this library names files to No-Intro instead, so hashing every ROM over the network is wasted.
CRC32_UNKNOWN = "00000000|crc"


def accepted_extensions(info_dir, probed, core):
    """Return every extension a core will take: the probe's valid_extensions plus the .info's.

    The probe's list is narrower than what RetroArch enforces -- explicit paths are not filtered on
    extension at all, so Virtual Jaguar reports "j64|jag" yet loads this library's .rom files.
    """
    declared = set(core_info_field(info_dir, core, "supported_extensions").split("|"))
    return (set(probed[core]["valid_extensions"]) | declared) - {""}


def validate_system(info_dir, probed, core, extensions):
    """Return the reasons a core cannot launch the extensions its system declares.

    Turns breakage that otherwise waits for a human to click the game into a failed run.
    """
    accepted = accepted_extensions(info_dir, probed, core)

    reasons = []
    for extension in extensions:
        # RetroArch matches on the final suffix only, so Pico-8's compound "p8.png" is a "png".
        effective = extension.rsplit(".", 1)[-1].lower()
        if effective == "zip":
            # block_extract hands the core the archive unopened. That breaks a core expecting the
            # extracted ROM (Dolphin) but suits an arcade core, whose romset is a multi-file .zip it
            # opens itself and lists among its extensions -- hence the second condition.
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

    Read from the .info rather than duplicated in the systems table, so it cannot drift from the
    installed core. Memoised because systems sharing a core would each reparse the file.
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

    Longest match wins, so "Celeste.p8.png" is labelled "Celeste", not "Celeste.p8". None when the
    file is not launchable content for this system.
    """
    lowered = name.lower()
    for extension in sorted(extensions, key=len, reverse=True):
        suffix = "." + extension.lower()
        if lowered.endswith(suffix):
            return name[: -len(suffix)]
    return None


def disc_entry(directory, extensions):
    """Return the disc a visible subdirectory of a system directory should launch.

    3DO and GameCube only: Opera and Dolphin swap discs themselves, so their multi-disc games sit in
    a visible directory with no .m3u. The playlist points at disc 1 and the label stays the
    directory name, which is also what the art is cached under. Elsewhere the directory is
    dot-prefixed and never reaches here.
    """
    discs = sorted(
        entry.path
        for entry in os.scandir(directory)
        if entry.is_file() and content_label(entry.name, extensions) is not None
    )
    if not discs:
        return None
    return next((disc for disc in discs if "(Disc 1)" in disc), discs[0])


def system_items(
    names, game_cores, system_dir, emit_system_dir, extensions, core_path, core_name, db_name
):
    """Build the playlist items for one system directory.

    Scanned at system_dir, written under emit_system_dir; equal for a same-host run. names maps
    romset shortname -> full title on arcade systems, game_cores maps label -> (core_path,
    core_name) for titles the system's core cannot launch; both empty elsewhere.
    """
    items = []
    for entry in sorted(os.scandir(system_dir), key=lambda e: e.name.lower()):
        # Hidden per-game directories hold the discs of a multi-disc game; the .m3u beside them
        # is the launchable entry.
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
            # Label arcade romsets by title, not MAME id; the path stays the romset file. The
            # title's board-id suffix is hidden by label_display_mode 3, as "(USA)" is elsewhere.
            label = names.get(label, label)
            # A .zip is listed by its own path, not "archive.zip#rom.sfc" as the scanner writes
            # it: RetroArch resolves a bare archive on load, and this never opens one over NFS.
            path = entry.path

        # Onto the target's mount. path is always under system_dir.
        path = emit_system_dir + path[len(system_dir):]

        # Only core_path differs; db_name stays the system's, so art resolves off the one playlist.
        item_core_path, item_core_name = game_cores.get(label, (core_path, core_name))

        items.append(
            {
                "path": path,
                "label": label,
                "core_path": item_core_path,
                "core_name": item_core_name,
                "crc32": CRC32_UNKNOWN,
                "db_name": db_name,
            }
        )
    return items


def is_generated_playlist(path, library_dir):
    """Whether this .lpl is one this generator wrote, rather than one the user built.

    RetroArch's own playlists land in the same directory with nothing in the filename to tell them
    apart, so ownership comes from the content: only a generated playlist points scan_content_dir
    inside the ROM library. The answer decides whether a file is deleted, so uncertainty means keep.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            playlist = json.load(handle)
    except (OSError, ValueError):
        return False
    if not isinstance(playlist, dict):
        return False

    scanned = playlist.get("scan_content_dir") or ""
    # commonpath raises rather than returning a mismatch on a relative path, which would take
    # down a run that merely walked past a playlist carrying one.
    if not isinstance(scanned, str) or not os.path.isabs(scanned):
        return False
    return os.path.commonpath([scanned, library_dir]) == library_dir


def prune_playlists(playlist_dir, library_dir, systems):
    """Remove the generated playlists of systems that games_retroarch_systems no longer lists.

    tasks/retroarch.yml deletes the dropped system's core, so a left-behind .lpl would go on
    offering the system with every entry pointing at a missing file. Only .lpl files directly in
    this directory and only ones this generator wrote: favourites and history live in builtin/.
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
    # Target-mount overrides; all default to a same-host run.
    emit_library_dir = config.get("emit_library_dir", library_dir)
    emit_system_dirs = config.get("emit_system_dirs", {})
    core_suffix = config.get("core_filename_suffix", "_libretro.so")
    # Romset -> title map, applied only to systems whose core is in arcade_name_cores. Both absent
    # by default, so elsewhere the lookup never happens and labels stay the filename.
    arcade_name_cores = set(config.get("arcade_name_cores", []))
    arcade_names = {}
    if config.get("arcade_names_path"):
        with open(config["arcade_names_path"], encoding="utf-8") as handle:
            arcade_names = json.load(handle)

    # An unmounted share looks like an empty directory, which would empty every playlist.
    if not os.path.isdir(library_dir):
        sys.exit("%s: ROM library is not a directory" % library_dir)

    # The probe covers every installed core and the role installs every core the table names, so an
    # unanswered core means the two disagree. game_cores is held to the same bar, or it would write
    # entries pointing at a missing core file.
    declared = {spec["core"] for _, spec in systems}
    declared.update(core for _, spec in systems for core in spec.get("game_cores", {}).values())
    unknown = sorted(declared - set(probed))
    if unknown:
        sys.exit("no installed core reported itself as: %s" % ", ".join(unknown))

    # Whole table before writing anything, so problems are reported together rather than one failed
    # run at a time. A game_cores core launches the system's content, so it faces the same
    # extensions.
    problems = [
        "%s: %s" % (system, reason)
        for system, spec in systems
        for core in [spec["core"], *sorted(set(spec.get("game_cores", {}).values()))]
        for reason in validate_system(info_dir, probed, core, spec["extensions"])
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
        # The filename is what RetroArch displays; db_name is what it resolves thumbnails by, and
        # what retroarch-fetch-thumbnails.py reads to pick the cache directory. thumbnail_db splits
        # the two for a system whose art the repository publishes under another name.
        playlist_name = "%s.lpl" % system
        db_name = "%s.lpl" % spec.get("thumbnail_db", system)
        core_path = os.path.join(cores_dir, "%s%s" % (core, core_suffix))
        emit_system_dir = os.path.join(emit_library_dir, emit_system_dirs.get(system, system))
        # A missing .info costs only a cosmetic label.
        core_name = core_info_field(info_dir, core, "display_name", default=core)
        names = arcade_names if core in arcade_name_cores else {}
        # label -> (core_path, core_name) for titles this system's core cannot launch.
        game_cores = {
            label: (
                os.path.join(cores_dir, "%s%s" % (game_core, core_suffix)),
                core_info_field(info_dir, game_core, "display_name", default=game_core),
            )
            for label, game_core in spec.get("game_cores", {}).items()
        }
        items = system_items(
            names,
            game_cores,
            system_dir,
            emit_system_dir,
            spec["extensions"],
            core_path,
            core_name,
            db_name,
        )

        # Never replace an existing playlist with an empty one: scanning to nothing means a wrong
        # extension list or a half-mounted share, neither worth discarding a good playlist over.
        if not items:
            print("skipped %s: no content matched %s" % (system, spec["extensions"]), file=sys.stderr)
            continue

        # After the empty guard, so a half-mounted share reports as the skip above rather than as
        # drift. A game_cores label matching nothing is inert while still reading as a fix.
        stale = sorted(set(game_cores) - {item["label"] for item in items})
        if stale:
            sys.exit(
                "%s: game_cores name labels the directory does not contain: %s"
                % (system, ", ".join(stale))
            )

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
            # Where in-app "Refresh Playlist" rescans, and the marker prune_playlists reads,
            # so it takes the target's mount.
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

        # Bytes, not text: a playlist RetroArch scanned is not necessarily valid UTF-8, and
        # decoding one to test whether it is current would fail before it could be replaced.
        path = os.path.join(playlist_dir, playlist_name)
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
