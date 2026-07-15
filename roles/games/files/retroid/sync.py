#!/usr/bin/env python3
"""Mirror the games role's managed RetroArch config onto a Retroid Pocket Flip 2 over adb.

The role converges a desktop's RetroArch install (cores, BIOS, a curated subset of retroarch.cfg,
per-core overrides and options, generated playlists). The Flip 2 runs stock Android with ES-DE, where
Ansible cannot, so this reproduces that convergence from the outside: it reads the role's own
defaults/main.yml as the source of truth, applies the Android divergences in profile.yml, and
reconciles the result onto the device (add/update the managed items, delete the ones that were
dropped, leave everything else the device has alone).

Not run by any playbook. Run it by hand on a host that mounts the ROM library, with the device on
USB and its `adb` authorisation granted. adb is installed by the dev role.

    ./sync.py --library-dir /path/to/rom-library            # real run
    ./sync.py --library-dir /path/to/rom-library --dry-run  # build + plan, no device writes

What it owns, mirroring the role's ownership semantics:

  * retroarch.cfg: only the enumerated keys are set (updated in place, appended if new) and the
    dropped keys removed; every other line the device has is preserved.
  * playlists: regenerated with device paths (the device's ES-DE short-name ROM dirs, and each
    core_path under the app-private cores dir), and stale managed .lpl (ones whose scan_content_dir is
    inside the device ROM dir, for a system no longer in the table) removed. Hand-built playlists are
    left alone.
  * BIOS: additive push from the library, no deletes.
  * thumbnails: additive push from the library, off by default (--push-thumbnails). The frontend here
    is ES-DE, which scrapes its own media; RetroArch's thumbnail cache is seen only when browsing
    inside RetroArch itself. The generated playlists are likewise RetroArch-only, but still pushed.
  * ES-DE emulators: each system's <alternativeEmulator> in its gamelist.xml is pinned to the core the
    role prefers (profile.yml esde_cores), so ES-DE launches our core, not its default.
  * ROM library (--roms only): each library system is mirrored onto ROMS/<short name>, deleting device
    games the library dropped and resending only what is missing (adb push --sync), so the long
    transfer resumes after an interruption. Off by default; it is hundreds of GB over USB.

Cores are NOT managed here: the sdcard and emulated storage are mounted noexec, so RetroArch can only
dlopen a core from the app-private dir the in-app Core Updater fills, which adb cannot write. Install
the cores the table needs with that updater; the generated playlists point their core_path at it, and
ES-DE is pointed at the same cores by name.

RetroArch and ES-DE are force-stopped for the run, since both rewrite what they own (retroarch.cfg,
gamelist.xml) on exit; reopen whichever is used afterwards.

The device library_names and the pad indices are the two things this cannot derive; see README.md.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROLE_DEFAULTS = os.path.normpath(os.path.join(HERE, "..", "..", "defaults", "main.yml"))
GENERATOR = os.path.normpath(os.path.join(HERE, "..", "retroarch-generate-playlists.py"))
# A rendered stand-in for the sdcard UUID when --dry-run runs with no device attached.
DRY_RUN_UUID = "SDCARD"

CFG_LINE = re.compile(r"^\s*([\w.]+)\s*=\s*(.*)$")


# --------------------------------------------------------------------------- model


def load_yaml(path):
    import yaml  # PyYAML; ships with Ansible, which the dev host already has.

    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def build_model(defaults, profile):
    """Apply the profile's transforms to the role defaults, returning the Android config."""
    systems = dict(defaults["games_retroarch_systems"])
    for name in profile["systems_remove"]:
        systems.pop(name, None)
    for name, spec in (profile.get("systems_set") or {}).items():
        systems[name] = spec
    for name, spec in (profile.get("systems_add") or {}).items():
        systems[name] = spec

    # Settings: base, less the dropped keys and the base's templated directory keys (which carry
    # unrenderable "{{ ... }}" values here), then the Android overrides, the explicit device
    # directories, and the pad's rewind/fast-forward bindings.
    drop = set(profile["settings_drop"])
    settings = {
        key: value
        for key, value in defaults["games_retroarch_required_settings"].items()
        if key not in drop and not (isinstance(value, str) and "{{" in value)
    }
    settings.update(profile["settings_override"])
    settings.update(profile["controller"])

    overrides = {
        core: spec
        for core, spec in defaults["games_retroarch_core_overrides"].items()
        if core not in set(profile["core_overrides_remove"])
    }
    for core, spec in (profile.get("core_overrides_set") or {}).items():
        overrides[core] = spec

    options = {core: dict(spec) for core, spec in defaults["games_retroarch_core_options"].items()}
    for core, spec in (profile.get("core_options_set") or {}).items():
        options.setdefault(core, {}).update(spec)

    cores = sorted({spec["core"] for spec in systems.values()})
    probe = profile["core_probe"]
    missing = [core for core in cores if core not in probe]
    if missing:
        sys.exit("core_probe is missing an entry for: %s" % ", ".join(missing))

    return {
        "systems": systems,
        "settings": settings,
        "overrides": overrides,
        "options": options,
        "probe": {core: probe[core] for core in cores},
        "library_names": {core: probe[core]["library_name"] for core in cores},
    }


def resolve_dirs(profile, uuid):
    """Render device_dirs and the app/cfg paths for a given sdcard uuid."""
    ctx = {
        "uuid": uuid,
        "package": profile["package"],
    }
    ctx["sdcard_root"] = profile["sdcard_root"].format(**ctx)
    ctx["app_files"] = profile["app_files"].format(**ctx)
    dirs = {name: tmpl.format(**ctx) for name, tmpl in profile["device_dirs"].items()}
    return ctx, dirs


# --------------------------------------------------------------------------- adb


class Device:
    """Thin adb wrapper. In dry-run it prints writes instead of performing them, and returns empty
    results for reads so the build still runs with no device attached."""

    def __init__(self, serial, dry_run):
        self.serial = serial
        self.dry_run = dry_run

    def _base(self):
        return ["adb"] + (["-s", self.serial] if self.serial else [])

    def _run(self, args, check=True, capture=True):
        return subprocess.run(
            self._base() + args,
            check=check,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
        )

    def read_shell(self, command):
        """Run a shell command on the device and return stdout, or "" on failure / dry-run."""
        result = self._run(["shell", command], check=False)
        return result.stdout if result.returncode == 0 else ""

    def exists(self, path):
        return self.read_shell("ls -d %s 2>/dev/null" % shq(path)).strip() != ""

    def list_dir(self, path):
        out = self.read_shell("ls -1 %s 2>/dev/null" % shq(path))
        return [line for line in out.splitlines() if line]

    def pull_text(self, path):
        """Return a device file's contents, or None if it is not there."""
        if not self.exists(path):
            return None
        result = self._run(["shell", "cat %s" % shq(path)], check=False)
        return result.stdout if result.returncode == 0 else None

    def mkdirs(self, *paths):
        for path in paths:
            self._write(["shell", "mkdir -p %s" % shq(path)], "mkdir -p %s" % path)

    def push(self, local, remote):
        self._write(["push", local, remote], "push %s -> %s" % (local, remote))

    def push_sync(self, local, remote, attempts=3):
        """Push only files newer than or absent on the device (adb push --sync); returns success.

        Used for the ROM mirror: a multi-hour transfer over USB drops the occasional connection, and
        --sync makes a retry resend only what did not land, so a transient failure is cheap to recover
        from. Returns True/False rather than raising so one glitchy system does not abort the whole run.
        """
        if self.dry_run:
            print("  [dry-run] push --sync %s -> %s" % (local, remote))
            return True
        for attempt in range(1, attempts + 1):
            if self._run(["push", "--sync", local, remote], check=False, capture=False).returncode == 0:
                return True
            print("  push --sync failed (attempt %d/%d)" % (attempt, attempts), file=sys.stderr)
        return False

    def stop_app(self, package):
        """Force-stop an app so it cannot rewrite what the sync pushes.

        RetroArch (config_save_on_exit) and ES-DE (rewrites gamelist.xml) both persist their in-memory
        state on exit, which would clobber the pushed retroarch.cfg / gamelists. Stopping them first is
        more reliable than asking the operator to.
        """
        if self.dry_run:
            print("  [dry-run] force-stop %s" % package)
            return
        self._run(["shell", "am force-stop %s" % shq(package)], check=False, capture=True)

    def push_text(self, text, remote):
        if self.dry_run:
            print("  [dry-run] write %d bytes -> %s" % (len(text.encode("utf-8")), remote))
            return
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write(text)
            tmp = handle.name
        try:
            self.push(tmp, remote)
        finally:
            os.unlink(tmp)

    def rm(self, path):
        self._write(["shell", "rm -rf %s" % shq(path)], "rm -rf %s" % path)

    def _write(self, args, description):
        if self.dry_run:
            print("  [dry-run] %s" % description)
            return
        self._run(args, check=True, capture=False)


def shq(path):
    """Single-quote a path for an adb shell command line."""
    return "'" + path.replace("'", "'\\''") + "'"


def require_adb():
    """Ensure adb is present and new enough to copy directory contents with `push <dir>/. <dst>`.

    That idiom lands the tree's contents in an existing destination (which repeated syncs need); on
    platform-tools older than 30 it can instead nest under an extra directory or push a literal ".",
    silently putting cores/BIOS/playlists where RetroArch will not find them. Ubuntu >= 24.04 ships
    34.x, so this only guards against an unexpectedly old adb.
    """
    if shutil.which("adb") is None:
        sys.exit("adb not found on PATH. Install it with the dev role (make dev), or apt install adb.")
    out = subprocess.run(["adb", "--version"], text=True, capture_output=True).stdout
    match = re.search(r"^Version (\d+)\.", out, re.MULTILINE)
    if match and int(match.group(1)) < 30:
        sys.exit("adb (platform-tools %s) is too old: `adb push <dir>/. <dst>` needs >= 30 to copy "
                 "directory contents into an existing directory. Upgrade adb." % match.group(1))


def discover_uuid(device):
    """Pick the removable sdcard's mount name under /storage."""
    candidates = [
        name
        for name in device.list_dir("/storage")
        if name not in ("emulated", "self") and re.fullmatch(r"[0-9A-Fa-f-]+", name)
    ]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        sys.exit("no removable sdcard found under /storage on the device.")
    sys.exit("multiple sdcard candidates under /storage (%s); pin sdcard_uuid in profile.yml."
             % ", ".join(candidates))


def discover_cfg(device, ctx):
    """Find the device's retroarch.cfg, trying the app-scoped path then the all-files one."""
    for path in (
        "%s/retroarch.cfg" % ctx["app_files"],
        "/storage/emulated/0/RetroArch/retroarch.cfg",
    ):
        if device.exists(path):
            return path
    # Default to the app-scoped path; the first sync creates it.
    return "%s/retroarch.cfg" % ctx["app_files"]


def override_config_dir(existing_cfg, cfg_path):
    """Where RetroArch reads per-core overrides from: rgui_config_directory if the device set it, else
    the config/ dir beside retroarch.cfg.

    RetroArch keeps per-core config/<library_name>/ overrides under its "Config Directory", which stock
    Android RetroArch points at /storage/emulated/0/RetroArch/config rather than the app files dir. An
    override pushed beside retroarch.cfg when rgui_config_directory names somewhere else is read from
    neither place and is silently ignored, so follow the device's own setting.
    """
    for line in (existing_cfg or "").splitlines():
        match = CFG_LINE.match(line)
        if match and match.group(1) == "rgui_config_directory":
            value = match.group(2).strip().strip('"')
            if value:
                return value
    return "%s/config" % os.path.dirname(cfg_path)


# --------------------------------------------------------------------------- cfg merge


def merge_cfg(existing, managed, drop):
    """Return retroarch.cfg text with the managed keys set and the dropped keys removed.

    Mirrors the role's per-key lineinfile: a managed key already in the file is rewritten in place,
    a new one is appended, a dropped one is deleted, and every other line is left untouched.
    """
    lines = existing.splitlines() if existing else []
    seen = set()
    out = []
    for line in lines:
        match = CFG_LINE.match(line)
        key = match.group(1) if match else None
        if key in drop:
            continue
        if key in managed:
            out.append('%s = "%s"' % (key, managed[key]))
            seen.add(key)
        else:
            out.append(line)
    appended = [key for key in managed if key not in seen]
    if appended:
        if out and out[-1].strip():
            out.append("")
        for key in appended:
            out.append('%s = "%s"' % (key, managed[key]))
    return "\n".join(out) + "\n"


def override_text(pairs):
    """Render a per-core .cfg/.opt: the role's Ansible-managed header, then sorted key = "value"."""
    header = "# Ansible managed\n"
    body = "".join('%s = "%s"\n' % (key, pairs[key]) for key in sorted(pairs))
    return header + body


# --------------------------------------------------------------------------- info


def fetch_info(profile, info_dir):
    """Download and extract the frontend .info set into info_dir.

    Any member ending in .info is kept under its basename, so the set arrives whether the zip stores
    the files at its root or under a subdirectory.
    """
    os.makedirs(info_dir, exist_ok=True)
    url = profile["info_zip_url"]
    print("  fetch %s" % url)
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read()
    with zipfile.ZipFile(io_bytes(data)) as archive:
        for member in archive.namelist():
            if member.endswith(".info"):
                with open(os.path.join(info_dir, os.path.basename(member)), "wb") as handle:
                    handle.write(archive.read(member))


def io_bytes(data):
    import io

    return io.BytesIO(data)


# --------------------------------------------------------------------------- generation


def generate_playlists(model, library_dir, dirs, profile, cores_ref, info_dir, playlist_dir):
    """Run the shared generator with an Android config, into playlist_dir."""
    os.makedirs(playlist_dir, exist_ok=True)
    config = {
        "library_dir": library_dir,
        "emit_library_dir": dirs["roms"],
        # The device's per-system ROM folders are ES-DE short names, not the library's No-Intro ones.
        "emit_system_dirs": profile.get("rom_dir_names") or {},
        "playlist_dir": playlist_dir,
        # core_path points at the app-private cores dir, the only place RetroArch can dlopen from.
        "cores_dir": cores_ref,
        "core_filename_suffix": profile["core_suffix"],
        "info_dir": info_dir,
        "cores": model["probe"],
        "systems": model["systems"],
    }
    result = subprocess.run(
        [sys.executable, GENERATOR],
        env={**os.environ, "RETROARCH_GENERATOR_CONFIG": json.dumps(config)},
        text=True,
        capture_output=True,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        sys.exit("playlist generation failed")


def write_overrides(model, staging_config):
    """Write config/<library_name>/<library_name>.{cfg,opt} for every configured core."""
    names = model["library_names"]
    for core, pairs in model["overrides"].items():
        write_core_file(staging_config, names.get(core, core), "cfg", pairs)
    for core, pairs in model["options"].items():
        write_core_file(staging_config, names.get(core, core), "opt", pairs)


def write_core_file(staging_config, library_name, extension, pairs):
    directory = os.path.join(staging_config, library_name)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "%s.%s" % (library_name, extension))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(override_text(pairs))


# --------------------------------------------------------------------------- reconcile


def stale_playlists(device, dirs, systems):
    """Device .lpl for a system no longer in the table that we can prove we generated."""
    stale = []
    for name in device.list_dir(dirs["playlists"]):
        if not name.endswith(".lpl") or name[: -len(".lpl")] in systems:
            continue
        text = device.pull_text("%s/%s" % (dirs["playlists"], name))
        if text is None:
            continue
        try:
            scanned = (json.loads(text).get("scan_content_dir") or "")
        except ValueError:
            continue
        # Boundary-aware, like the generator's commonpath check: a sibling sharing the prefix
        # (.../ROMS_BACKUP) is not inside the ROM dir and is not ours to delete.
        roms = dirs["roms"]
        if scanned == roms or scanned.startswith(roms + "/"):
            stale.append(name)
    return stale


# --------------------------------------------------------------------------- ROM library


# Files that live alongside ROMs but are not games and are not this sync's to delete: the Retroid
# firmware/frontend drops a systeminfo.txt in each system directory, and a mirror that pruned by
# "not in the library" would wrongly take it (and any similar per-system metadata) with it.
PRESERVE_IN_ROMS = {"systeminfo.txt"}


def device_rom_files(device, root):
    """Relative paths of every file under root on the device, recursive and including hidden entries.

    Uses find rather than list_dir's `ls -1`: `ls -1` omits dotfiles, so hidden multi-disc directories
    (.game/) and anything nested in a subdirectory would be invisible to the prune below and a renamed
    disc would accumulate beside its replacement. find sees them.
    """
    prefix = root.rstrip("/") + "/"
    out = device.read_shell("find %s -type f 2>/dev/null" % shq(root))
    return [line[len(prefix):] for line in out.splitlines() if line.startswith(prefix)]


def library_rom_files(src):
    """Relative paths of every file under a library system directory, matching device_rom_files."""
    files = set()
    for dirpath, _, names in os.walk(src):
        rel = os.path.relpath(dirpath, src)
        for name in names:
            files.add(name if rel == "." else os.path.join(rel, name))
    return files


def mirror_roms(device, library_dir, roms_root, rom_dir_names):
    """Mirror each library system directory onto ROMS/<short name>, replacing what the device has.

    Per system: delete the device files the library no longer carries (renamed or removed games), then
    push the library with --sync, which skips bytes already on the device. So the first run is a full
    copy, a re-run after an interruption resumes, and a renamed file replaces its old version rather
    than accumulating beside it. The prune is recursive and sees hidden entries, so multi-disc .game/
    directories and files nested in subdirectories are handled; device-managed metadata (PRESERVE_IN
    _ROMS) is left alone. Systems whose library directory is missing are skipped, not emptied.
    """
    failed = []
    for lib_name, dev_name in sorted(rom_dir_names.items()):
        src = os.path.join(library_dir, lib_name)
        if not os.path.isdir(src):
            print("  skip %s: no library directory" % lib_name)
            continue
        dst = "%s/%s" % (roms_root, dev_name)
        device.mkdirs(dst)
        wanted = library_rom_files(src)
        for rel in device_rom_files(device, dst):
            if os.path.basename(rel) in PRESERVE_IN_ROMS or rel in wanted:
                continue
            device.rm("%s/%s" % (dst, rel))
        print("Mirroring %s -> %s" % (lib_name, dev_name))
        if not device.push_sync(src + "/.", dst):
            failed.append(dev_name)
    if failed:
        sys.exit("%d system(s) did not fully mirror (transfer errors). Re-run to resume (--sync resends "
                 "only what is missing): %s" % (len(failed), ", ".join(failed)))


# --------------------------------------------------------------------------- ES-DE cores


ALT_EMULATOR = re.compile(r"<alternativeEmulator>.*?</alternativeEmulator>\s*", re.DOTALL)
XML_DECL = re.compile(r"(<\?xml[^>]*\?>\s*)")


def set_alt_emulator(existing, label):
    """Return gamelist.xml text with the per-system <alternativeEmulator> set to label.

    ES-DE writes <alternativeEmulator> as a second root element ahead of <gameList> (not valid single
    -root XML, so this is done as text, not with a parser). An existing block is replaced, otherwise
    the block is inserted after the XML declaration, and a missing gamelist is created with an empty
    <gameList/> that ES-DE fills on its next scan while keeping the emulator choice.
    """
    block = "<alternativeEmulator>\n\t<label>%s</label>\n</alternativeEmulator>\n" % label
    if not existing:
        return '<?xml version="1.0"?>\n%s<gameList />\n' % block
    if ALT_EMULATOR.search(existing):
        return ALT_EMULATOR.sub(lambda _: block, existing, count=1)
    if XML_DECL.search(existing):
        return XML_DECL.sub(lambda m: m.group(1) + block, existing, count=1)
    return block + existing


def configure_esde_cores(device, gamelists_dir, esde_cores):
    """Pin each system's ES-DE emulator to the games role's preferred core via its gamelist.xml."""
    for system, label in sorted(esde_cores.items()):
        system_dir = "%s/%s" % (gamelists_dir, system)
        path = "%s/gamelist.xml" % system_dir
        updated = set_alt_emulator(device.pull_text(path), label)
        device.mkdirs(system_dir)
        print("ES-DE %s -> %s" % (system, label))
        device.push_text(updated, path)


# --------------------------------------------------------------------------- main


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--library-dir", required=True, help="ROM library mount on this host")
    parser.add_argument("--profile", default=os.path.join(HERE, "profile.yml"))
    parser.add_argument("--serial", default="", help="adb device serial (adb -s)")
    parser.add_argument("--dry-run", action="store_true", help="build and plan, no device writes")
    parser.add_argument("--skip-bios", action="store_true", help="do not push the BIOS set")
    parser.add_argument("--roms", action="store_true",
                        help="also mirror the ROM library onto the device's ES-DE ROMS tree (the long "
                             "transfer; off by default). Deletes device games the library dropped and "
                             "resumes with adb push --sync")
    parser.add_argument("--push-thumbnails", action="store_true",
                        help="push the RetroArch thumbnail cache (off by default: ES-DE, the frontend "
                             "here, uses its own scraped media, so RetroArch's cache is only seen when "
                             "browsing inside RetroArch itself)")
    args = parser.parse_args()

    if not os.path.isdir(args.library_dir):
        sys.exit("%s: ROM library is not a directory (is the mount up?)" % args.library_dir)

    profile = load_yaml(args.profile)
    defaults = load_yaml(ROLE_DEFAULTS)
    model = build_model(defaults, profile)
    device = Device(args.serial, args.dry_run)

    # A dry run never touches adb, so it neither requires the binary nor probes for a device.
    if args.dry_run:
        online = False
    else:
        require_adb()
        online = device.read_shell("echo ok").strip() == "ok"

    if online:
        uuid = profile["sdcard_uuid"] or discover_uuid(device)
    elif args.dry_run:
        print("no device online; rendering paths with a stand-in sdcard uuid (%s)" % DRY_RUN_UUID)
        uuid = profile["sdcard_uuid"] or DRY_RUN_UUID
    else:
        sys.exit("no device reachable over adb (check the cable and `adb devices`).")

    # Stop the apps that persist state on exit before writing anything they own, so neither RetroArch
    # (retroarch.cfg) nor ES-DE (gamelist.xml) overwrites the pushed result.
    if online:
        device.stop_app(profile["package"])
        device.stop_app(profile["esde_package"])

    ctx, dirs = resolve_dirs(profile, uuid)
    # The directory keys can only be resolved once the sdcard uuid is known, so they are folded into
    # the managed settings here rather than in build_model.
    for key, name in profile["directory_settings"].items():
        model["settings"][key] = dirs[name]

    cfg_path = discover_cfg(device, ctx) if online else "%s/retroarch.cfg" % ctx["app_files"]
    existing_cfg = device.pull_text(cfg_path) if online else None
    config_dir = override_config_dir(existing_cfg, cfg_path)
    cores_ref = profile["cores_ref"].format(package=profile["package"])

    print("Device sdcard: %s" % ctx["sdcard_root"])
    print("retroarch.cfg: %s" % cfg_path)
    print("overrides:     %s" % config_dir)

    staging = tempfile.mkdtemp(prefix="retroid-sync-")
    try:
        info_dir = os.path.join(staging, "info")
        playlist_dir = os.path.join(staging, "playlists")
        config_stage = os.path.join(staging, "config")

        # .info drives the generator's extension validation. Best-effort in a dry run (no network):
        # fall back to the host's flatpak info set. Cores themselves are neither fetched nor pushed:
        # the sdcard and emulated storage are noexec, so RetroArch can only dlopen a core from the
        # app-private dir the in-app Core Updater fills; cores_ref points playlists at that dir.
        if not args.dry_run:
            print("Fetching core info...")
            fetch_info(profile, info_dir)
        if not os.path.isdir(info_dir):
            info_dir = host_info_dir()

        print("Generating playlists...")
        generate_playlists(model, args.library_dir, dirs, profile, cores_ref, info_dir, playlist_dir)

        print("Writing per-core overrides and options...")
        write_overrides(model, config_stage)

        # The sdcard dirs are public storage; adb can always create them.
        device.mkdirs(*dirs.values())

        # retroarch.cfg and the per-core overrides live in the app files dir, which adb may not be
        # allowed to write on Android 11+. Attempt it, but treat a denial as the documented manual
        # fallback rather than a crash, and carry on with the sdcard content either way.
        print("Reconciling retroarch.cfg...")
        merged = merge_cfg(existing_cfg, model["settings"], set(profile["settings_drop"]))
        try:
            device.mkdirs(os.path.dirname(cfg_path), config_dir)
            device.push_text(merged, cfg_path)
            if os.path.isdir(config_stage):
                device.push(config_stage + "/.", config_dir)
        except subprocess.CalledProcessError:
            print(
                "WARNING: could not write %s (adb is denied the app files dir). Grant RetroArch "
                "all-files access so its config moves to /storage/emulated/0/RetroArch/, or copy the "
                "staged retroarch.cfg and config/ in with an on-device file manager. See README.md."
                % cfg_path,
                file=sys.stderr,
            )

        # Push the staged playlists. The trailing "/." copies contents into the existing dir
        # (require_adb checks adb is new enough for this).
        device.push(playlist_dir + "/.", dirs["playlists"])

        bios_src = os.path.join(args.library_dir, "_BIOS", "retroarch-system-folder")
        if not args.skip_bios and os.path.isdir(bios_src):
            print("Pushing BIOS set...")
            device.push(bios_src + "/.", dirs["system"])
        thumbs_src = os.path.join(args.library_dir, "_Thumbnails")
        if args.push_thumbnails and os.path.isdir(thumbs_src):
            print("Pushing thumbnail cache...")
            device.push(thumbs_src + "/.", dirs["thumbnails"])

        # Remove stale managed playlists (a system that left the table). Cores are never touched: they
        # live in the app-private dir adb cannot reach, and are the in-app Core Updater's to manage.
        if online:
            for name in stale_playlists(device, dirs, model["systems"]):
                print("Removing stale playlist %s" % name)
                device.rm("%s/%s" % (dirs["playlists"], name))
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    # ES-DE emulator choices and (optionally) the ROM library. These need no staging, so they run
    # outside the temp dir's lifetime; the ROM mirror in particular is a multi-hour transfer. Run them
    # under --dry-run too (Device prints the planned writes) so a preview of the destructive --roms
    # deletes and pushes is not silently skipped for want of a device.
    print("Configuring ES-DE preferred cores...")
    configure_esde_cores(device, profile["esde_gamelists_dir"], profile["esde_cores"])
    if args.roms:
        print("Mirroring ROM library (the long transfer; resumable with --sync)...")
        mirror_roms(device, args.library_dir, dirs["roms"], profile["rom_dir_names"])

    print("Done. RetroArch and ES-DE were stopped for the sync; reopen whichever you use.")


def host_info_dir():
    """The host's flatpak libretro .info dir, used as a fallback in dry runs."""
    return os.path.expanduser(
        "~/.local/share/flatpak/app/org.libretro.RetroArch/current/active/files/share/libretro/info"
    )


if __name__ == "__main__":
    main()
