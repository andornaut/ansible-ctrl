#!/usr/bin/env python3
"""Fill the shared thumbnail cache for every entry in the generated playlists.

RetroArch's on-demand downloader fetches only what is scrolled past, leaving a game never browsed
without art on any host. Matching is by playlist label against the repository's No-Intro names,
with two fallbacks: base-game art for a dump the repository does not carry (translation, fix,
homebrew re-release), and the cart itself for Pico-8. See title_key, disambiguate, and main.

One line per thumbnail written on stdout; games left with no box art on stderr. Operator summary
is in files/README.md.
"""

import gzip
import html
import http.client
import json
import os
import re
import shutil
import sys
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HOST = "thumbnails.libretro.com"

# The three types RetroArch looks for, named as the repository names them. Box art first because it
# is the only one a gap is reported against -- it is what the browser shows.
BOXART = "Named_Boxarts"
TYPES = (BOXART, "Named_Titles", "Named_Snaps")

# Stripped to "_" by RetroArch before a lookup and by the repository before publishing, so
# "Ys Book I & II" is "Ys Book I _ II.png" on both sides.
INVALID = re.compile(r'[&*/:`<>?\\|"]')

HREF = re.compile(r'href="([^"]+\.png)"', re.IGNORECASE)

# Every parenthesised group in a No-Intro name, in order: the (Region), then each (Tag).
TAG = re.compile(r"\(([^)]*)\)")

# Tells a region tag ("(USA)") from a qualifier that merely comes first ("(Homebrew)"), so only the
# former narrows an ambiguous match.
REGIONS = frozenset(
    (
        "usa",
        "europe",
        "japan",
        "world",
        "asia",
        "australia",
        "brazil",
        "canada",
        "china",
        "france",
        "germany",
        "greece",
        "hong kong",
        "italy",
        "korea",
        "latin america",
        "mexico",
        "netherlands",
        "new zealand",
        "norway",
        "poland",
        "portugal",
        "russia",
        "scandinavia",
        "spain",
        "sweden",
        "taiwan",
        "uk",
        "unknown",
        "denmark",
        "finland",
        "belgium",
        "austria",
        "switzerland",
        "ireland",
    )
)

# Sized for the largest directory listing, the slowest request this makes.
TIMEOUT = 60

WORKERS = 8

# One reused connection per worker thread, plus the requests that went unanswered. Process-wide
# because fetch() runs on the pool's threads.
CONNECTIONS = threading.local()
UNREACHABLE = []
UNREACHABLE_LOCK = threading.Lock()


def name_key(name):
    """Return the filename a label is cached under, matched case-insensitively.

    The sanitizing is what both sides do, so this is an exact match. Case is folded because
    No-Intro capitalizes an interior article ("Sonic The Hedgehog"), not worth failing over.
    """
    return INVALID.sub("_", name).lower()


def title_key(name):
    """Return a key for the game underneath a dump's (Region) and (Tag) suffixes.

    The looser key, for a dump the repository does not carry: the base game's box art is right for
    a copy tagged "(Wolt fast fix by Nexus)". Punctuation goes too, the other way a re-release
    drifts ("Fix-It Felix Jr." against "Fix It Felix Jr.").
    """
    return re.sub(r"[^a-z0-9]", "", name.split(" (")[0].lower())


def tags_of(name):
    """The parenthesised groups of a name, in order, lowercased."""
    return [group.strip().lower() for group in TAG.findall(name)]


def regions_of(name):
    """The region set a name carries, or empty when its first group is not a region.

    The region is the first parenthesised group, itself comma-separated ("USA, Europe"). A name
    with no group, or one leading with a qualifier (Homebrew, Demo), is never matched on region.
    """
    groups = tags_of(name)
    if not groups:
        return frozenset()
    parts = frozenset(part.strip() for part in groups[0].split(","))
    return parts if parts <= REGIONS else frozenset()


def disambiguate(label, candidates):
    """Choose among several dumps sharing a title, or None if none shares the label's region.

    A title key matches every regional dump, and within one region they carry the same box art, so
    the choice is only which name to fetch that cover under. Never crosses regions: rather than
    hand a USA cover to a Japanese dump, the match is declined.
    """
    want = regions_of(label)
    if not want:
        return None
    same_region = [name for name in candidates if regions_of(name) == want]
    if not same_region:
        return None
    label_tags = tags_of(label)

    def rank(name):
        tags = tags_of(name)
        shared = 0
        for mine, theirs in zip(label_tags, tags, strict=False):
            if mine != theirs:
                break
            shared += 1
        # Most tags shared with the label, then the plainest dump, then by name so the pick does
        # not depend on how the listing came back.
        return (-shared, len(tags), name)

    return min(same_region, key=rank)


def fetch(path):
    """Return the body the repository publishes at a path, or None when it publishes nothing there.

    404 is an answer, and the common one. Anything else is recorded rather than returned, so a run
    that could not reach the server does not look like one with nothing to fetch. Retried once on a
    fresh connection, a dropped keep-alive being the ordinary failure.

    Connections are kept because a first run makes one request per thumbnail and the handshake
    costs more than the transfer. gzip helps the HTML listings; the PNGs ignore it.
    """
    for attempt in (1, 2):
        connection = getattr(CONNECTIONS, "connection", None)
        if connection is None:
            connection = http.client.HTTPSConnection(HOST, timeout=TIMEOUT)
            CONNECTIONS.connection = connection
        try:
            connection.request("GET", path, headers={"Accept-Encoding": "gzip"})
            with connection.getresponse() as response:
                body = response.read()
                if response.status == 404:
                    return None
                if response.status != 200:
                    raise http.client.HTTPException(f"HTTP {response.status}")
                if response.getheader("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return body
        except (http.client.HTTPException, OSError) as error:
            connection.close()
            CONNECTIONS.connection = None
            if attempt == 2:
                with UNREACHABLE_LOCK:
                    UNREACHABLE.append(f"{path}: {error}")
    return None


def listing(system, kind):
    """Return every name the repository publishes for a system, without the .png.

    Empty for a system it does not carry at all (Pico-8), which is not an error: the caller then
    reports the gap per game.
    """
    body = fetch(f"/{urllib.parse.quote(system)}/{kind}/")
    if body is None:
        return []
    return [
        urllib.parse.unquote(html.unescape(name))[: -len(".png")]
        for name in HREF.findall(body.decode("utf-8", "replace"))
    ]


def index(names):
    """Return the two lookups a name is resolved through, in descending order of confidence.

    Built over the whole listing up front, so an ambiguous title key is resolved deliberately
    rather than to whichever name was seen first, which would swap two regional dumps' art.
    """
    names_by, titles = {}, {}
    for name in names:
        names_by.setdefault(name_key(name), []).append(name)
        titles.setdefault(title_key(name), []).append(name)
    return names_by, titles


def resolve(label, indexes):
    """Return (published name, whether it is a looser match than the label), or (None, False)."""
    exact = indexes[0].get(name_key(label), [])
    if len(exact) == 1:
        return exact[0], False

    candidates = indexes[1].get(title_key(label), [])
    if len(candidates) == 1:
        return candidates[0], True
    if len(candidates) > 1:
        chosen = disambiguate(label, candidates)
        if chosen is not None:
            return chosen, True
    return None, False


def install(source, destination):
    """Write a thumbnail under a temporary name, so an interrupted run leaves no half file."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    # with_name rather than +: a Path does not concatenate with a string, and
    # the suffix has to land on the file name rather than on the directory.
    partial = destination.with_name(destination.name + ".part")
    if isinstance(source, bytes):
        partial.write_bytes(source)
    else:
        shutil.copyfile(source, partial)
    partial.replace(destination)


def missing_slots(playlist_dir, thumbnails_dir):
    """Return (system, kind, label, content path, destination) for every thumbnail not yet cached.

    The system comes from each item's db_name, what RetroArch looks the thumbnail up by, not the
    filename: a hand-built collection names its own system per item under a filename the repository
    does not publish. Read leniently like the generator does -- a scanned playlist is not
    necessarily valid UTF-8, and one unreadable file should not abandon the rest.
    """
    slots = []
    overridden = set()
    for path in sorted(Path(playlist_dir).iterdir()):
        playlist = path.name
        if not playlist.endswith(".lpl") or not path.is_file():
            continue
        try:
            with path.open(encoding="utf-8", errors="replace") as handle:
                items = json.load(handle).get("items", [])
        except (OSError, ValueError):
            print(f"skipped {playlist}: not a readable playlist", file=sys.stderr)
            continue

        for item in items:
            system = Path(item.get("db_name") or playlist).stem
            # A db_name differing from the filename is a deliberate thumbnail_db override,
            # asserting the repository publishes that system. The ordinary case asserts nothing,
            # so the two are checked differently in main().
            if system != path.stem:
                overridden.add(system)
            for kind in TYPES:
                destination = Path(thumbnails_dir) / system / kind / (INVALID.sub("_", item["label"]) + ".png")
                if not destination.exists():
                    slots.append((system, kind, item["label"], item["path"], destination))
    return slots, overridden


def main():
    config = json.loads(os.environ["RETROARCH_THUMBNAILS_CONFIG"])

    # The share carries only what is group-readable. New directories inherit the group from the
    # cache's setgid bit but not the mode, so under a 027 umask the art would go invisible to every
    # host mounting the library. Set here rather than inherited from whatever invoked the play.
    os.umask(0o022)

    slots, overridden = missing_slots(config["playlist_dir"], config["thumbnails_dir"])
    downloads = []

    # A PNG content file is its own box art: a Pico-8 cart is a picture of its label with the code
    # in the pixels. Read off the path rather than a systems-table flag, and only for box art --
    # the repository publishes no Pico-8 directory, so the other two would 404 on every cart.
    for slot in slots:
        system, kind, label, path, destination = slot
        if path.lower().endswith(".png"):
            if kind == BOXART:
                install(path, destination)
                print(f"{system}: {label} (from the cart)")
        else:
            downloads.append(slot)

    # One listing per system and type, only where a gap remains.
    wanted = sorted({(system, kind) for system, kind, _, _, _ in downloads})
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        indexes = dict(zip(wanted, pool.map(lambda pair: index(listing(*pair)), wanted), strict=False))

    # An override exists precisely to name a directory the repository has, so one publishing
    # nothing is a wrong thumbnail_db value. Unchecked it degrades into "no box art is published"
    # for the whole system, blaming the library's naming instead. A misspelt key falls back to the
    # system's own name and shows up as the system reverting to its displayed name.
    misnamed = sorted(
        system
        for system in overridden
        if any(pair[0] == system for pair in wanted)
        and not any(names_by for (s, _), (names_by, _) in indexes.items() if s == system)
    )
    if misnamed:
        print(
            f"{len(misnamed)} system(s) name a thumbnail_db the repository does not publish, "
            "so no art can resolve for them:",
            file=sys.stderr,
        )
        for system in misnamed:
            print(f"  {system}", file=sys.stderr)
        return 1

    def download(slot):
        system, kind, label, _, destination = slot
        name, loosely = resolve(label, indexes[(system, kind)])
        if name is None:
            return slot, None, False
        body = fetch(f"/{urllib.parse.quote(system)}/{kind}/{urllib.parse.quote(name)}.png")
        if not body:
            return slot, None, False
        install(body, destination)
        return slot, name, loosely

    unresolved = set()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for slot, name, loosely in pool.map(download, downloads):
            system, kind, label, _, _ = slot
            if name is None:
                # An unpublished title screen or gameplay snap is not a gap anyone sees.
                if kind == BOXART:
                    unresolved.add((system, label))
                continue
            # Name the looser match: it is the art of the dump before it was translated or
            # patched, a judgement worth seeing.
            print("{}: {}{}".format(system, label, (f" as {name}") if loosely else ""))

    # An unreachable repository resolves every game to "no art published", which from here looks
    # exactly like a complete cache. Fail rather than report convergence.
    if UNREACHABLE:
        print(
            f"{len(UNREACHABLE)} request(s) to {HOST} went unanswered, so nothing can be said about what is missing:",
            file=sys.stderr,
        )
        for failure in UNREACHABLE[:5]:
            print(f"  {failure}", file=sys.stderr)
        return 1

    if unresolved:
        print(
            f"no box art is published for {len(unresolved)} game(s). Either it is a dump the "
            "repository does not carry, or the library has named it in a way the No-Intro "
            "standard does not:",
            file=sys.stderr,
        )
        for system, label in sorted(unresolved):
            print(f"  [{system}] {label}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
