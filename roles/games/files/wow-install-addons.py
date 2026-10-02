#!/usr/bin/env python3
"""Install World of Warcraft addons from Wago into every game version a WoW install holds.

Reads WOW_ADDONS_CONFIG, a JSON document:

    {"wow_dir": "/home/user/.local/games/Lutris/battlenet/drive_c/Program Files (x86)/World of Warcraft",
     "flavors": {"_retail_": "retail", "_classic_beta_": "forever"},
     "addons": ["baganator"]}

`flavors` maps each game version directory under `wow_dir` to the name Wago publishes that
version's releases under. A directory that is absent is skipped, and so is a version an addon
publishes no release for.

The release is read from the addon's Wago page (https://addons.wago.io/addons/<slug>), whose
Inertia page data carries the newest release per version as `props.metadata.recent_releases`.
Wago's API needs a key and CurseForge refuses non-browser clients, so the page is the keyless
route.

Each install writes `Interface/AddOns/.wago-<slug>.json`, naming the release and the top-level
directories it extracted. An install whose marker names the current release and whose
directories are all present is left alone; otherwise the directories the marker and the archive
name are replaced. Nothing outside them is touched, so saved variables under WTF/ survive.

Prints one line per install and nothing when every addon is current.
"""

import html
import io
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

PAGE_URL = "https://addons.wago.io/addons/{slug}"
# Cloudflare refuses urllib's own User-Agent.
USER_AGENT = "ansible-ctrl"
PAGE_DATA = re.compile(r'<div id="app" data-page="([^"]*)"')


def fetch(url):
    # The download link comes from the page, so its scheme is checked rather than trusted.
    if not url.startswith("https://"):
        raise ValueError(f"refusing to fetch a non-https URL {url!r}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return response.read()


def releases(page):
    """Return Wago's newest release per game version from an addon page's HTML."""
    match = PAGE_DATA.search(page)
    if match is None:
        raise ValueError("the page carries no Inertia page data")
    data = json.loads(html.unescape(match.group(1)))
    return {flavor: release for flavor, release in data["props"]["metadata"]["recent_releases"].items() if release}


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


def current(addons_dir, marker, label):
    if not marker.exists():
        return False
    state = json.loads(marker.read_text())
    return state.get("label") == label and all((addons_dir / name).is_dir() for name in state.get("dirs", []))


def install(addons_dir, slug, label, payload):
    """Replace the addon's directories in addons_dir with the archive's, then write the marker."""
    marker = addons_dir / f".wago-{slug}.json"
    archive = zipfile.ZipFile(io.BytesIO(payload))
    dirs = top_level_dirs(archive)
    previous = json.loads(marker.read_text()).get("dirs", []) if marker.exists() else []
    if not all(plain(name) for name in previous):
        raise ValueError(f"{marker} names a directory outside {addons_dir}")
    staging = Path(tempfile.mkdtemp(prefix=f".wago-{slug}-", dir=addons_dir.parent))
    try:
        archive.extractall(staging)
        for name in sorted(set(previous) | set(dirs)):
            target = addons_dir / name
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            elif target.exists() or target.is_symlink():
                target.unlink()
        for name in dirs:
            (staging / name).rename(addons_dir / name)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    marker.write_text(json.dumps({"label": label, "dirs": dirs}) + "\n")


def main():
    cfg = json.loads(os.environ["WOW_ADDONS_CONFIG"])
    wow_dir = Path(cfg["wow_dir"])
    present = {name: flavor for name, flavor in cfg["flavors"].items() if (wow_dir / name).is_dir()}
    if not present:
        return
    downloads = {}
    for slug in cfg["addons"]:
        available = releases(fetch(PAGE_URL.format(slug=slug)).decode())
        for name, flavor in sorted(present.items()):
            release = available.get(flavor)
            if release is None:
                continue
            addons_dir = wow_dir / name / "Interface" / "AddOns"
            label = release["label"]
            if current(addons_dir, addons_dir / f".wago-{slug}.json", label):
                continue
            # Wago signs one link per version for the same file, so the label keys the cache.
            if label not in downloads.setdefault(slug, {}):
                downloads[slug][label] = fetch(release["download_link"])
            addons_dir.mkdir(parents=True, exist_ok=True)
            install(addons_dir, slug, label, downloads[slug][label])
            print(f"{slug} {label} -> {name}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        sys.exit(f"wow-install-addons: {error}")
