#!/usr/bin/env python3
"""Fill the shared thumbnail cache for every entry in the generated playlists.

RetroArch's own on-demand downloader only fetches what is scrolled past, so a game never browsed
has no thumbnail on any host. It stays on where the mount is writable, as the fallback for a game
added between runs, but this is what keeps the cache complete.

The library and the repository both name a game to the No-Intro standard, so the ordinary case is
an exact match on the playlist label, and a game that does not match exactly is worth knowing
about: it usually means the library has named it in a way the standard does not. Two things still
need resolving beyond that, and neither is a naming disagreement:

  * A dump the repository has never heard of: a translation, a fix, a homebrew re-release. Its
    (Region) and (Tag) suffixes match no published release, but the game underneath them does, and
    the base game's art is the right art for it.
  * A Pico-8 cart, which is already a picture of itself. The repository carries no Pico-8 art at
    all, and none of it could: the .p8.png in the library *is* the label image.

Prints one line per thumbnail written, so stdout is the change report. Games that end the run with
no box art go to stderr.
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

HOST = "thumbnails.libretro.com"

# The three thumbnail types RetroArch looks for, named as the repository names them. Box art is
# first because it is the one a missing thumbnail is reported against: it is what the browser
# shows, and a game with no title screen or gameplay snap still looks right without them.
BOXART = "Named_Boxarts"
TYPES = (BOXART, "Named_Titles", "Named_Snaps")

# The characters RetroArch strips out of a label before looking a thumbnail up, and the repository
# strips out of a name before publishing it. Both write "_", so "Ys Book I & II" is cached as
# "Ys Book I _ II.png" on both sides.
INVALID = re.compile(r'[&*/:`<>?\\|"]')

HREF = re.compile(r'href="([^"]+\.png)"', re.IGNORECASE)

# Every parenthesised group in a No-Intro name, in order: the (Region), then each (Tag).
TAG = re.compile(r"\(([^)]*)\)")

# The regions a name can carry in its first parenthesised group, lowercased. Used to tell a region
# tag ("(USA)") from a qualifier that merely comes first ("(Homebrew)"), so only the former narrows
# an ambiguous match.
REGIONS = frozenset((
    "usa", "europe", "japan", "world", "asia", "australia", "brazil", "canada", "china",
    "france", "germany", "greece", "hong kong", "italy", "korea", "latin america", "mexico",
    "netherlands", "new zealand", "norway", "poland", "portugal", "russia", "scandinavia",
    "spain", "sweden", "taiwan", "uk", "unknown", "denmark", "finland", "belgium", "austria",
    "switzerland", "ireland",
))

# Enough for the largest directory listing (the Genesis box art index runs to ~1400 entries), which
# is the slowest request this makes.
TIMEOUT = 60

WORKERS = 8

# One connection per worker thread, reused across its requests, and the requests that could not be
# answered at all. Both are process-wide because fetch() is called from the pool's threads.
CONNECTIONS = threading.local()
UNREACHABLE = []
UNREACHABLE_LOCK = threading.Lock()


def name_key(name):
    """Return the filename a label is cached under, matched case-insensitively.

    The sanitizing is what RetroArch and the repository both do, so this is an exact match on the
    name. Only the case is given away, because a No-Intro name capitalizes an interior article
    ("Sonic The Hedgehog") and it is not worth failing over.
    """
    return INVALID.sub("_", name).lower()


def title_key(name):
    """Return a key for the game underneath a dump's (Region) and (Tag) suffixes.

    The looser of the two keys, and the one that answers for a dump the repository does not carry:
    a translation, a fix, a homebrew re-release. The box art of "Final Fantasy Tactics - The War of
    the Lions (USA)" is the right art for the copy of it tagged "(Wolt fast fix by Nexus)", and
    there is no other name that copy could be asking for. Punctuation goes too, which is the other
    way a re-release drifts ("Fix-It Felix Jr." against "Fix It Felix Jr.").
    """
    return re.sub(r"[^a-z0-9]", "", name.split(" (")[0].lower())


def tags_of(name):
    """The parenthesised groups of a name, in order, lowercased."""
    return [group.strip().lower() for group in TAG.findall(name)]


def regions_of(name):
    """The region set a name carries, or empty when its first group is not a region.

    The region is the first parenthesised group, itself a comma-separated list ("USA, Europe").
    Empty for a name with no group, or one whose first group is a qualifier (Homebrew, Demo)
    rather than a region, so such a name is never matched on region.
    """
    groups = tags_of(name)
    if not groups:
        return frozenset()
    parts = frozenset(part.strip() for part in groups[0].split(","))
    return parts if parts <= REGIONS else frozenset()


def disambiguate(label, candidates):
    """Choose among several dumps sharing a title, or None if none shares the label's region.

    A title key deliberately matches every regional dump of a game, so it often returns more than
    one name. Within a single region they all carry the same box art (a revision, a disc, a
    re-release under a slightly different spelling), so once the field is narrowed to the label's
    own region the choice is only which name to fetch that one cover under, and any of them is
    right. It never crosses regions: a dump the label shares no region with is dropped, and if that
    leaves nothing the match is declined rather than hand a USA cover to a Japanese dump.
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
        for mine, theirs in zip(label_tags, tags):
            if mine != theirs:
                break
            shared += 1
        # Most tags shared with the label first, then the plainest dump (fewest tags), then a
        # stable order by name so the pick never depends on how the listing came back.
        return (-shared, len(tags), name)

    return min(same_region, key=rank)


def fetch(path):
    """Return the body the repository publishes at a path, or None when it publishes nothing there.

    404 is an answer, and the common one: the repository carries no art for this game, or none for
    this system at all. Anything else is the repository failing to answer, which is not the same
    thing and is recorded rather than returned: a run that fetched nothing because it could not
    reach the server must not look like a run that had nothing to fetch. Retried once on a fresh
    connection first, a dropped keep-alive being the ordinary way this fails.

    The connection is kept: a handshake costs more than the transfer it carries here (~430ms), and a
    first run makes one request per thumbnail. gzip because the listings are HTML indexes and
    compress about 12x; the thumbnails are PNG and ignore it.
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
                    raise http.client.HTTPException("HTTP %d" % response.status)
                if response.getheader("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return body
        except (http.client.HTTPException, OSError) as error:
            connection.close()
            CONNECTIONS.connection = None
            if attempt == 2:
                with UNREACHABLE_LOCK:
                    UNREACHABLE.append("%s: %s" % (path, error))
    return None


def listing(system, kind):
    """Return every name the repository publishes for a system, without the .png.

    Empty for a system the repository does not carry at all (Pico-8), which is not an error: the
    caller then has nothing to match against and says so, per game.
    """
    body = fetch("/%s/%s/" % (urllib.parse.quote(system), kind))
    if body is None:
        return []
    return [
        urllib.parse.unquote(html.unescape(name))[: -len(".png")]
        for name in HREF.findall(body.decode("utf-8", "replace"))
    ]


def index(names):
    """Return the two lookups a name is resolved through, in descending order of confidence.

    Both are built over the whole listing before anything is looked up, so that a title key
    matching more than one published name is resolved deliberately rather than to whichever of them
    happened to be seen first: within the label's region any of them carries the same cover, and a
    name from another region is never offered at all. That is what stops two regional dumps of one
    game from being given each other's art.
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
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    partial = destination + ".part"
    if isinstance(source, bytes):
        with open(partial, "wb") as handle:
            handle.write(source)
    else:
        shutil.copyfile(source, partial)
    os.replace(partial, destination)


def missing_slots(playlist_dir, thumbnails_dir):
    """Return (system, kind, label, content path, destination) for every thumbnail not yet cached.

    The system comes from each item's db_name, which is what RetroArch looks the thumbnail up by,
    rather than from the playlist's filename: they are the same for a generated playlist, but a
    collection built by hand in RetroArch (which the generator leaves alone) names its own system
    per item, and its filename is not one the repository publishes anything under.

    Read the way the generator reads them, and for the same reason: a playlist RetroArch scanned
    itself is not necessarily valid UTF-8, and one unreadable file is not worth abandoning the rest.
    """
    slots = []
    for playlist in sorted(os.listdir(playlist_dir)):
        path = os.path.join(playlist_dir, playlist)
        if not playlist.endswith(".lpl") or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                items = json.load(handle).get("items", [])
        except (OSError, ValueError):
            print("skipped %s: not a readable playlist" % playlist, file=sys.stderr)
            continue

        for item in items:
            system = os.path.splitext(item.get("db_name") or playlist)[0]
            for kind in TYPES:
                destination = os.path.join(
                    thumbnails_dir, system, kind, INVALID.sub("_", item["label"]) + ".png"
                )
                if not os.path.exists(destination):
                    slots.append((system, kind, item["label"], item["path"], destination))
    return slots


def main():
    config = json.loads(os.environ["RETROARCH_THUMBNAILS_CONFIG"])

    # The cache is served over the network, and the share only carries what is in the library's
    # group and group-readable. The directories below the cache inherit the group from its setgid
    # bit, but not the mode: created under a 027 umask they come out unreadable to the group, and
    # the art goes invisible to every host that mounts the library. Set here rather than inherited
    # from whatever invoked the play.
    os.umask(0o022)

    slots = missing_slots(config["playlist_dir"], config["thumbnails_dir"])
    downloads = []

    # A system whose content files are themselves PNGs is its own box art: a Pico-8 cart is a
    # picture of its label with the code hidden in the pixels, so the file already in the library is
    # the image. Asked of the content's own path rather than of a flag in the systems table, because
    # that is where the answer already is.
    #
    # Its title screen and gameplay snap are not asked of the repository at all: it publishes no
    # Pico-8 directory, so those are a request that 404s on every run, forever, for every cart.
    for slot in slots:
        system, kind, label, path, destination = slot
        if path.lower().endswith(".png"):
            if kind == BOXART:
                install(path, destination)
                print("%s: %s (from the cart)" % (system, label))
        else:
            downloads.append(slot)

    # One listing per system and type, and only for the ones that still have a gap.
    wanted = sorted({(system, kind) for system, kind, _, _, _ in downloads})
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        indexes = dict(zip(wanted, pool.map(lambda pair: index(listing(*pair)), wanted)))

    def download(slot):
        system, kind, label, _, destination = slot
        name, loosely = resolve(label, indexes[(system, kind)])
        if name is None:
            return slot, None, False
        body = fetch(
            "/%s/%s/%s.png"
            % (urllib.parse.quote(system), kind, urllib.parse.quote(name))
        )
        if not body:
            return slot, None, False
        install(body, destination)
        return slot, name, loosely

    unresolved = set()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for slot, name, loosely in pool.map(download, downloads):
            system, kind, label, _, _ = slot
            if name is None:
                # Only the box art is worth reporting a game for. A title screen or a gameplay snap
                # the repository never published is not a gap anyone sees.
                if kind == BOXART:
                    unresolved.add((system, label))
                continue
            # A looser match took a name the library does not use, so say which, once. It is the art
            # of the dump before it was translated or patched, and that is a judgement to be able to
            # see rather than one to make silently.
            print("%s: %s%s" % (system, label, (" as %s" % name) if loosely else ""))

    # Fail rather than report a converged cache: a repository that cannot be reached resolves every
    # game to "no art published", which is what a complete cache also looks like from here.
    if UNREACHABLE:
        print(
            "%d request(s) to %s went unanswered, so nothing can be said about what is missing:"
            % (len(UNREACHABLE), HOST),
            file=sys.stderr,
        )
        for failure in UNREACHABLE[:5]:
            print("  %s" % failure, file=sys.stderr)
        return 1

    if unresolved:
        print(
            "no box art is published for %d game(s). Either it is a dump the repository does not "
            "carry, or the library has named it in a way the No-Intro standard does not:"
            % len(unresolved),
            file=sys.stderr,
        )
        for system, label in sorted(unresolved):
            print("  [%s] %s" % (system, label), file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
