#!/usr/bin/env python3
"""Install World of Warcraft addons from CurseForge into every game version a WoW install holds.

Reads WOW_ADDONS_CONFIG, a JSON document:

    {"wow_dir": "/home/user/.local/games/Lutris/battlenet/drive_c/Program Files (x86)/World of Warcraft",
     "flavors": {"_retail_": 517, "_forever_": 88568},
     "addons": [{"name": "baganator", "curseforge_id": 914482}]}

`flavors` maps each game version directory under `wow_dir` to the CurseForge gameVersionTypeId
that version's addon files are tagged with. A directory that is absent is skipped, and so is a
version an addon publishes no release for. `name` labels the addon's marker and output line;
`curseforge_id` is the "Project ID" on its curseforge.com page.

The release is read from CurseForge's site API, which needs no key: the project's file
listing, newest first, gives per version the newest file whose releaseType is 1 (release, not
beta or alpha). The site's search endpoint does need a key, hence the numeric project ID.

Each archive is streamed to a temporary file under `wow_dir`, downloaded once per run however
many versions share it, and deleted once the addon's versions are done.

Each install writes `Interface/AddOns/.curseforge-<name>.json`, naming the file and the
top-level directories it extracted. An install whose marker names the current file and whose
directories are all present is left alone; otherwise the directories the marker and the archive
name are replaced. Nothing outside them is touched, so saved variables under WTF/ survive.

Prints one line per install and nothing when every addon is current.
"""

import json
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

FILES_URL = (
    "https://www.curseforge.com/api/v1/mods/{project}/files"
    "?pageIndex={page}&pageSize={size}&sort=dateCreated&sortDescending=true&removeAlphas=true"
)
DOWNLOAD_URL = "https://www.curseforge.com/api/v1/mods/{project}/files/{file}/download"
# The listing returns at most 50 files per page whatever pageSize asks for.
PAGE_SIZE = 50
RELEASE = 1
USER_AGENT = "ansible-ctrl"


class HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # The download redirects to a CDN URL carrying a CurseForge key, so the refusal names
        # no URL.
        if not newurl.startswith("https://"):
            raise ValueError("refusing a redirect to a non-https URL")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_https(url):
    if not url.startswith("https://"):
        raise ValueError(f"refusing to fetch a non-https URL {url!r}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    return urllib.request.build_opener(HttpsOnlyRedirect).open(request, timeout=60)


def fetch_json(url):
    with open_https(url) as response:
        return json.load(response)


def download(directory, url):
    """Stream url into a new file in directory and return its path."""
    with open_https(url) as response, tempfile.NamedTemporaryFile(dir=directory, suffix=".zip", delete=False) as out:
        shutil.copyfileobj(response, out, 1 << 20)
    return Path(out.name)


def releases(wanted, project):
    """Return the project's newest release file per gameVersionTypeId in wanted."""
    found = {}
    page = 0
    while True:
        listing = fetch_json(FILES_URL.format(project=project, page=page, size=PAGE_SIZE))
        files = listing["data"]
        for entry in files:
            if entry["releaseType"] != RELEASE:
                continue
            for type_id in wanted.intersection(entry["gameVersionTypeIds"]):
                found.setdefault(type_id, entry)
        page += 1
        if wanted.issubset(found) or not files or page * PAGE_SIZE >= listing["pagination"]["totalCount"]:
            return found


def plain(name):
    """Whether name is one path component that is not hidden, so it stays inside AddOns/."""
    return bool(name) and not name.startswith(".") and "/" not in name and "\\" not in name


def top_level_dirs(archive):
    names = {name.split("/", 1)[0] for name in archive.namelist()}
    for name in names:
        if not plain(name):
            raise ValueError(f"the archive has an unexpected top-level entry {name!r}")
    if any("/" not in name for name in archive.namelist()):
        raise ValueError("the archive has a file outside an addon directory")
    return sorted(names)


def marker_path(addons_dir, name):
    return addons_dir / f".curseforge-{name}.json"


# CLEANUP (added 2026-11-11): the Wago installer's marker, read once as the addon's previous
# directories and then removed. Delete once no host in the games group has an
# Interface/AddOns/.wago-*.json under any game version directory.
def wago_marker_path(addons_dir, name):
    return addons_dir / f".wago-{name}.json"


def current(addons_dir, name, file_id):
    marker = marker_path(addons_dir, name)
    if not marker.exists():
        return False
    state = json.loads(marker.read_text())
    return state.get("file") == file_id and all((addons_dir / d).is_dir() for d in state.get("dirs", []))


def previous_dirs(addons_dir, name):
    for marker in (marker_path(addons_dir, name), wago_marker_path(addons_dir, name)):
        if marker.exists():
            dirs = json.loads(marker.read_text()).get("dirs", [])
            if not all(plain(d) for d in dirs):
                raise ValueError(f"{marker} names a directory outside {addons_dir}")
            return dirs
    return []


def install(addons_dir, name, release, archive_path):
    """Replace the addon's directories in addons_dir with the archive's, then write the marker."""
    with zipfile.ZipFile(archive_path) as archive:
        dirs = top_level_dirs(archive)
        previous = previous_dirs(addons_dir, name)
        staging = Path(tempfile.mkdtemp(prefix=f".curseforge-{name}-", dir=addons_dir.parent))
        try:
            archive.extractall(staging)
            for d in sorted(set(previous) | set(dirs)):
                target = addons_dir / d
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                elif target.exists() or target.is_symlink():
                    target.unlink()
            for d in dirs:
                (staging / d).rename(addons_dir / d)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    state = {"file": release["id"], "name": release["displayName"], "dirs": dirs}
    marker_path(addons_dir, name).write_text(json.dumps(state) + "\n")
    wago_marker_path(addons_dir, name).unlink(missing_ok=True)


def install_addon(wow_dir, present, downloads_dir, name, project):
    available = releases(set(present.values()), project)
    downloads = {}
    try:
        for version, type_id in sorted(present.items()):
            release = available.get(type_id)
            if release is None:
                continue
            addons_dir = wow_dir / version / "Interface" / "AddOns"
            if current(addons_dir, name, release["id"]):
                continue
            if release["id"] not in downloads:
                url = DOWNLOAD_URL.format(project=project, file=release["id"])
                downloads[release["id"]] = download(downloads_dir, url)
            addons_dir.mkdir(parents=True, exist_ok=True)
            install(addons_dir, name, release, downloads[release["id"]])
            print(f"{name} {release['displayName']} -> {version}")
    finally:
        for path in downloads.values():
            path.unlink(missing_ok=True)


def main():
    cfg = json.loads(os.environ["WOW_ADDONS_CONFIG"])
    wow_dir = Path(cfg["wow_dir"])
    present = {name: type_id for name, type_id in cfg["flavors"].items() if (wow_dir / name).is_dir()}
    if not present:
        return
    # On the same filesystem as the AddOns directories, so a multi-gigabyte archive never lands
    # in a tmpfs /tmp.
    downloads_dir = Path(tempfile.mkdtemp(prefix=".curseforge-downloads-", dir=wow_dir))
    try:
        for addon in cfg["addons"]:
            name = addon["name"]
            if not plain(name):
                raise ValueError(f"the addon name {name!r} is not a plain file name")
            install_addon(wow_dir, present, downloads_dir, name, addon["curseforge_id"])
    finally:
        shutil.rmtree(downloads_dir, ignore_errors=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        sys.exit(f"wow-install-addons: {error}")
