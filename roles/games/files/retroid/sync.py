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
  * playlists: regenerated with device paths, and stale managed .lpl (ones whose scan_content_dir is
    inside the device ROM dir, for a system no longer in the table) removed. Hand-built playlists are
    left alone.
  * cores: the arm64-v8a set the table needs, and dropped cores removed.
  * BIOS / thumbnails: additive push from the library, no deletes.

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
import urllib.error
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
        "cores": cores,
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


# --------------------------------------------------------------------------- cores / info


def fetch_cores(profile, cores, cores_dir):
    """Download and unzip the arm64-v8a build of each core into cores_dir.

    A core with no Android nightly, or a zip whose member is named unexpectedly, is collected rather
    than raised on: one missing core must not abort the whole sync with a traceback after most of the
    set has already downloaded. The failures are reported together and stop the run before any device
    write, so the device is never left with a partial core set.
    """
    os.makedirs(cores_dir, exist_ok=True)
    base = profile["buildbot_url"].format(abi=profile["core_abi"])
    suffix = profile["core_suffix"]
    failed = []
    for core in cores:
        name = "%s%s" % (core, suffix)
        url = "%s/%s.zip" % (base, name)
        print("  fetch %s" % url)
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                data = response.read()
            with zipfile.ZipFile(io_bytes(data)) as archive:
                # The buildbot names the member after the zip, but read whichever .so it holds rather
                # than assuming, so a naming change degrades to a clear error not a KeyError.
                member = next((n for n in archive.namelist() if n.endswith(".so")), None)
                if member is None:
                    raise KeyError("no .so in archive")
                with open(os.path.join(cores_dir, name), "wb") as handle:
                    handle.write(archive.read(member))
        except (urllib.error.URLError, OSError, zipfile.BadZipFile, KeyError) as error:
            failed.append("%s (%s)" % (core, error))
    if failed:
        sys.exit("could not fetch %d core(s) for %s:\n  %s"
                 % (len(failed), profile["core_abi"], "\n  ".join(failed)))


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


def generate_playlists(model, library_dir, dirs, profile, info_dir, playlist_dir):
    """Run the shared generator with an Android config, into playlist_dir."""
    os.makedirs(playlist_dir, exist_ok=True)
    config = {
        "library_dir": library_dir,
        "emit_library_dir": dirs["roms"],
        "playlist_dir": playlist_dir,
        "cores_dir": dirs["cores"],
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


def dropped_cores(device, dirs, model, suffix, known_cores):
    """Device cores this role once managed but no longer runs, to remove.

    Scoped to known_cores (every core any version of the role's table names) so a core the user
    installed in-app for an unmanaged system is never deleted: the device cores directory is shared
    with RetroArch's own Core Updater, unlike the desktop's role-owned one.
    """
    keep = {"%s%s" % (core, suffix) for core in model["cores"]}
    dropped = []
    for name in device.list_dir(dirs["cores"]):
        if not name.endswith(suffix) or name in keep:
            continue
        if name[: -len(suffix)] in known_cores:
            dropped.append(name)
    return dropped


# --------------------------------------------------------------------------- main


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--library-dir", required=True, help="ROM library mount on this host")
    parser.add_argument("--profile", default=os.path.join(HERE, "profile.yml"))
    parser.add_argument("--serial", default="", help="adb device serial (adb -s)")
    parser.add_argument("--dry-run", action="store_true", help="build and plan, no device writes")
    parser.add_argument("--skip-cores", action="store_true", help="do not fetch/push cores")
    parser.add_argument("--skip-bios", action="store_true", help="do not push the BIOS set")
    parser.add_argument("--skip-thumbnails", action="store_true", help="do not push the thumbnail cache")
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

    ctx, dirs = resolve_dirs(profile, uuid)
    # The directory keys can only be resolved once the sdcard uuid is known, so they are folded into
    # the managed settings here rather than in build_model.
    for key, name in profile["directory_settings"].items():
        model["settings"][key] = dirs[name]

    cfg_path = discover_cfg(device, ctx) if online else "%s/retroarch.cfg" % ctx["app_files"]
    config_dir = "%s/config" % os.path.dirname(cfg_path)
    suffix = profile["core_suffix"]

    print("Device sdcard: %s" % ctx["sdcard_root"])
    print("retroarch.cfg: %s" % cfg_path)

    staging = tempfile.mkdtemp(prefix="retroid-sync-")
    try:
        info_dir = os.path.join(staging, "info")
        playlist_dir = os.path.join(staging, "playlists")
        config_stage = os.path.join(staging, "config")

        # Cores + .info. In dry-run with no network wanted, the generator still validates against the
        # profile's static extensions, so info is best-effort: fall back to the host's flatpak info.
        if not args.skip_cores and not args.dry_run:
            print("Fetching cores (%s)..." % profile["core_abi"])
            fetch_cores(profile, model["cores"], os.path.join(staging, "cores"))
        if not args.dry_run:
            print("Fetching core info...")
            fetch_info(profile, info_dir)
        if not os.path.isdir(info_dir):
            info_dir = host_info_dir()

        print("Generating playlists...")
        generate_playlists(model, args.library_dir, dirs, profile, info_dir, playlist_dir)

        print("Writing per-core overrides and options...")
        write_overrides(model, config_stage)

        # The sdcard dirs are public storage; adb can always create them.
        device.mkdirs(*dirs.values())

        # retroarch.cfg and the per-core overrides live in the app files dir, which adb may not be
        # allowed to write on Android 11+. Attempt it, but treat a denial as the documented manual
        # fallback rather than a crash, and carry on with the sdcard content either way.
        print("Reconciling retroarch.cfg...")
        existing = device.pull_text(cfg_path) if online else None
        merged = merge_cfg(existing, model["settings"], set(profile["settings_drop"]))
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

        # Push the staged sdcard trees. The trailing "/." copies contents into the existing dir
        # (require_adb checks adb is new enough for this).
        if not args.skip_cores:
            device.push(os.path.join(staging, "cores") + "/.", dirs["cores"])
        if not args.dry_run and os.path.isdir(info_dir):
            device.push(info_dir + "/.", dirs["info"])
        device.push(playlist_dir + "/.", dirs["playlists"])

        bios_src = os.path.join(args.library_dir, "_BIOS", "retroarch-system-folder")
        if not args.skip_bios and os.path.isdir(bios_src):
            print("Pushing BIOS set...")
            device.push(bios_src + "/.", dirs["system"])
        thumbs_src = os.path.join(args.library_dir, "_Thumbnails")
        if not args.skip_thumbnails and os.path.isdir(thumbs_src):
            print("Pushing thumbnail cache...")
            device.push(thumbs_src + "/.", dirs["thumbnails"])

        # Deletes: dropped cores and stale managed playlists. Dropped cores are scoped to cores the
        # role has ever named (the desktop table's cores plus this Android set), so a user's own
        # in-app core for an unmanaged system is never removed.
        if online:
            known_cores = {spec["core"] for spec in defaults["games_retroarch_systems"].values()}
            known_cores |= set(model["cores"])
            for name in dropped_cores(device, dirs, model, suffix, known_cores):
                print("Removing dropped core %s" % name)
                device.rm("%s/%s" % (dirs["cores"], name))
            for name in stale_playlists(device, dirs, model["systems"]):
                print("Removing stale playlist %s" % name)
                device.rm("%s/%s" % (dirs["playlists"], name))
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    print("Done. Close RetroArch on the device before this run, and reopen it after.")


def host_info_dir():
    """The host's flatpak libretro .info dir, used as a fallback in dry runs."""
    return os.path.expanduser(
        "~/.local/share/flatpak/app/org.libretro.RetroArch/current/active/files/share/libretro/info"
    )


if __name__ == "__main__":
    main()
