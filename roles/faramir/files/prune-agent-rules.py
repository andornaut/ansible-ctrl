#!/usr/bin/env python3
"""Reduce each agent deny list to what faramir's own record says it wrote there.

faramir keeps a record of the rules it last rendered into each agent file, and its merge
takes out anything in that record the current render no longer produces. A rule written
before the record existed is in neither, so it accumulates: the file keeps refusing paths
nothing declares any more, in spellings that stopped working. This removes them.

What is deleted is every deny entry the record does not name, so a deny rule added to one
of these files by hand goes too. That is the intent: after this, an agent deny list is
exactly what faramir renders and nothing else. The originals are copied aside first.

Claude Code is the only one of the six agents this role installs whose deny rules are an
array of strings, so it is the only one this changes. opencode and Kilo Code keep theirs as
an object keyed by pattern, and the record holds only strings that were array elements, so
it names no key of that shape and there is nothing to compare one against. pi keeps its
rules in an extension rather than in JSON, and codex and Antigravity have no rule file at
all. Each of those is reported as skipped and left alone.

    prune-agent-rules.py [--check] <config-dir>

Prints one JSON object: what was removed, per file.
"""

import argparse
import json
import os
import shutil
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path

# What faramir last rendered into each agent file, keyed by that file's absolute path. Its
# name and shape are internal/agentcfg/writtenrules.go's; a host whose faramir predates it
# has no such file, and there is then nothing here that can tell faramir's rules from the
# operator's, so the run reports that and changes nothing.
RECORD = "written-rules.json"

# The key whose array of strings is a deny list, wherever it appears in these documents.
DENY_KEY = "deny"


def load_json(path):
    """Parse path, or return None when it is missing or is not JSON."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def prune_document(value, keep, left_alone):
    """Walk a parsed document, dropping deny-list entries outside keep. Returns what came out.

    The length of each deny list holding anything but strings is appended to left_alone and
    the list itself is not touched: the record describes no list of that shape, and a
    partially pruned one would be worse than one left whole.
    """
    removed = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == DENY_KEY and isinstance(nested, list):
                if not all(isinstance(entry, str) for entry in nested):
                    left_alone.append(len(nested))
                    continue
                value[key] = [entry for entry in nested if entry in keep]
                removed.extend(entry for entry in nested if entry not in keep)
                continue
            removed.extend(prune_document(nested, keep, left_alone))
    elif isinstance(value, list):
        for element in value:
            removed.extend(prune_document(element, keep, left_alone))
    return removed


def has_deny_list(value):
    """Whether the document holds an array-shaped deny list at all."""
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == DENY_KEY and isinstance(nested, list):
                return True
            if has_deny_list(nested):
                return True
    elif isinstance(value, list):
        return any(has_deny_list(element) for element in value)
    return False


def serialise(document):
    """Render a document the way faramir renders one, so the next install rewrites nothing.

    The last writer over these files is MergeJSON, an encoder with SetEscapeHTML(false) and
    a two-space indent across a map, so: sorted keys, a trailing newline, and the two line
    separators below escaped and nothing else. < > and & stay literal, and everything else
    non-ASCII Go emits as UTF-8, which is why ensure_ascii is off: left on it escapes every
    non-ASCII character, and a file in that spelling reads as changed on every run for as
    long as a value holds one. The two Go does escape are put back by hand.
    """
    text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False)
    for literal, escaped in (("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        text = text.replace(literal, escaped)
    return text + "\n"


def backup_path(path, stamp):
    """Where the original is copied before it is rewritten."""
    return path.with_name(f"{path.name}.pruned-{stamp}.bak")


def prune_file(path, keep, stamp, check):
    """Prune one file, reporting what came out of it and where the original went."""
    document = load_json(path)
    if document is None:
        return {"path": str(path), "skipped": "unreadable or not JSON"}
    if not has_deny_list(document):
        return {"path": str(path), "skipped": "no array-shaped deny list"}

    left_alone = []
    removed = prune_document(document, keep, left_alone)
    result = {"path": str(path), "removed": sorted(removed)}
    # Named rather than passed over: an empty removed list otherwise reads as "nothing stale
    # here" for the one shape the walk deliberately declines to touch.
    if left_alone:
        result["skipped"] = "a deny list holding entries that are not strings was left whole"
    if not removed or check:
        return result

    # copy2 carries the mode across and not the ownership, and this runs as root. Without the
    # chown the operator's own backup arrives root-owned, unreadable to them wherever the
    # directory is not setgid to a group they are in.
    original = path.stat()
    backup = backup_path(path, stamp)
    shutil.copy2(path, backup)
    os.chown(backup, original.st_uid, original.st_gid)

    # Replaced rather than rewritten in place: this file carries the agent's PreToolUse hook,
    # and a truncating write interrupted partway leaves the agent running with no hook and no
    # deny list. The owner and mode go onto the temporary file first, both because a file
    # arriving owned by root stops the agent reading it and because os.replace keeps whatever
    # the temporary file has.
    temporary = path.with_name(f".{path.name}.pruning")
    temporary.write_text(serialise(document), encoding="utf-8")
    os.chown(temporary, original.st_uid, original.st_gid)
    temporary.chmod(stat.S_IMODE(original.st_mode))
    temporary.replace(path)
    result["backup"] = str(backup)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config_dir", help="faramir's configuration directory")
    parser.add_argument("--check", action="store_true", help="report what would come out, change nothing")
    args = parser.parse_args()

    record = load_json(Path(args.config_dir) / RECORD)
    if not isinstance(record, dict):
        print(
            json.dumps(
                {
                    "changed": False,
                    "files": [],
                    "note": f"no readable {RECORD} under {args.config_dir}, so nothing distinguishes "
                    f"faramir's rules from the operator's and nothing was changed",
                }
            )
        )
        return 0

    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    results = []
    named = 0
    for name, rules in sorted(record.items()):
        path = Path(name)
        if not path.is_file():
            continue
        named += 1
        # An entry of another shape is not an empty one. Read as "faramir wrote nothing here"
        # it would take out every rule in the file, faramir's own included, so a record entry
        # this cannot read leaves the file alone instead.
        if not isinstance(rules, list):
            results.append({"path": str(path), "skipped": f"record entry is {type(rules).__name__}, not a list"})
            continue
        results.append(prune_file(path, set(rules), stamp, args.check))

    removed_total = sum(len(result.get("removed", [])) for result in results)
    payload = {
        "changed": removed_total > 0,
        "removed_total": removed_total,
        "files": [result for result in results if result.get("removed") or result.get("skipped")],
    }
    # A record naming nothing on disk compares nothing, which reports identically to a host
    # already converged. Said rather than left to read as success.
    if named == 0:
        payload["note"] = f"{RECORD} under {args.config_dir} named no file that exists here, so nothing was compared"
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
