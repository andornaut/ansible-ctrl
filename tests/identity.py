# Fails on a task whose account is left to the connection, which is one that neither
# declares an account itself nor sits inside a block that declares one for it.
#
# Such a task runs as whoever ansible connects as. Over ssh that is the inventory's
# ansible_user and never varies; on a local connection it is whoever invoked ansible, so
# the same task is the operator on one run and root on the next. A task that touches
# per-user state, or a tool installed per user, then acts on the wrong account.
#
# The allowlist beside this file holds what has not been declared yet. It can only shrink:
# an entry matching nothing is an error, so a task that gains an identity has to lose its
# line here in the same commit.

import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
ALLOWLIST = pathlib.Path(__file__).with_name("identity-allowlist.txt")

# Leaves nothing behind, and answers the same whoever asks. `stat`, `find` and `slurp` are
# deliberately absent: they write nothing, but their answer is the account's, and a path it
# cannot traverse reads as absent rather than as an error.
READ_ONLY = frozenset(
    {
        "ansible.builtin.assert",
        "ansible.builtin.debug",
        "ansible.builtin.fail",
        "ansible.builtin.getent",
        "ansible.builtin.import_role",
        "ansible.builtin.import_tasks",
        "ansible.builtin.include_role",
        "ansible.builtin.include_tasks",
        "ansible.builtin.include_vars",
        "ansible.builtin.meta",
        "ansible.builtin.package_facts",
        "ansible.builtin.pause",
        "ansible.builtin.set_fact",
        "ansible.builtin.setup",
        "ansible.builtin.uri",
        "ansible.builtin.wait_for",
    }
)

# Everything ansible reads off a task that is not the module being called.
DIRECTIVES = frozenset(
    {
        "always",
        "any_errors_fatal",
        "args",
        "become",
        "become_flags",
        "become_method",
        "become_user",
        "block",
        "changed_when",
        "check_mode",
        "collections",
        "connection",
        "delay",
        "delegate_facts",
        "delegate_to",
        "diff",
        "environment",
        "failed_when",
        "ignore_errors",
        "listen",
        "loop",
        "loop_control",
        "module_defaults",
        "name",
        "no_log",
        "notify",
        "poll",
        "register",
        "rescue",
        "retries",
        "run_once",
        "tags",
        "throttle",
        "timeout",
        "until",
        "vars",
        "when",
        "with_dict",
        "with_fileglob",
        "with_items",
        "with_nested",
    }
)

INCLUDES = frozenset({"ansible.builtin.include_tasks", "ansible.builtin.import_tasks"})

MAX_DEPTH = 12


def reads_only(node, module):
    """Whether the module leaves nothing behind, so the account it ran as does not matter.

    `uri` is in the set because it usually fetches, but `dest` makes it write a file, and
    that file is owned by whoever the task ran as.
    """
    if module not in READ_ONLY:
        return False
    if module == "ansible.builtin.uri":
        spec = node[module]
        return not (isinstance(spec, dict) and "dest" in spec)
    return True


def module_of(task):
    for key in task:
        if key not in DIRECTIVES and not key.startswith("with_"):
            return key
    return "?"


ERRORS = []


def load(path):
    try:
        return yaml.safe_load(path.read_text()) or []
    except (OSError, yaml.YAMLError) as exc:
        ERRORS.append(f"unreadable, so nothing in it was checked: {path}: {exc}")
        return []


def declares(node):
    """Whether this level says anything about the account, `become: false` included.

    An explicit false is a decision: run as the connecting account, on purpose. Only a
    task that says nothing at all leaves the account to whoever started the run.
    """
    return "become" in node or "become_user" in node


def resolve_include(path, target):
    """Where ansible looks for an included file, or None.

    The role's `tasks/` first, then beside the including file: the two are the same for a
    file already under `tasks/`, and differ for a handler, whose relative include ansible
    resolves against `tasks/` rather than `handlers/`.
    """
    parts = pathlib.PurePath(path).parts
    candidates = []
    if len(parts) > 2 and parts[0] == "roles":
        candidates.append(ROOT / parts[0] / parts[1] / "tasks" / target)
    candidates.append((ROOT / path).parent / target)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def walk(node, path, declared, found, seen, depth=0, chain=()):
    """Collect leaf tasks, carrying the nearest declaration down the chain.

    `chain` is the call sites an included file was reached through, so a report names the
    task that has to gain the declaration and not only the helper that inherits it.
    """
    if not isinstance(node, dict):
        return
    if depth > MAX_DEPTH:
        ERRORS.append(f"nested deeper than {MAX_DEPTH}, so the rest went unchecked: {path}")
        return
    declared = declared or declares(node)

    nested = [key for key in ("block", "rescue", "always") if key in node]
    if nested:
        for key in nested:
            for child in node[key] or []:
                walk(child, path, declared, found, seen, depth + 1, chain)
        return

    module = module_of(node)
    if module in INCLUDES:
        spec = node[module]
        target = spec.get("file") if isinstance(spec, dict) else spec
        site = f"{path}::{node.get('name', '(unnamed)')}"
        # A computed name resolves per host, so it cannot be followed from here. That fails
        # the gate rather than passing every task in the file unchecked: name the file.
        if not isinstance(target, str) or "{{" in target:
            ERRORS.append(f"include target is computed, so nothing it holds was checked: {site} -> {target}")
            return
        included = resolve_include(path, target)
        if included is None:
            ERRORS.append(f"include target does not resolve, so nothing it holds was checked: {site} -> {target}")
            return
        rel = str(included.relative_to(ROOT))
        seen.add(rel)
        for child in load(included):
            walk(child, rel, declared, found, seen, depth + 1, (*chain, site))
        return

    if declared or reads_only(node, module):
        return
    found.append((*chain, f"{path}::{node.get('name', '(unnamed)')}"))


def scan(path, found, seen):
    doc = load(path)
    if not isinstance(doc, list):
        return
    rel = str(path.relative_to(ROOT))
    for item in doc:
        if not isinstance(item, dict):
            continue
        if "hosts" in item:
            for section in ("pre_tasks", "tasks", "post_tasks"):
                for child in item.get(section) or []:
                    walk(child, rel, declares(item), found, seen, 0)
            continue
        walk(item, rel, False, found, seen, 0)


def collect():
    """Every task whose account comes from the connection rather than the task."""
    entries = (
        sorted(ROOT.glob("roles/*/tasks/*.yml"))
        + sorted(ROOT.glob("roles/*/handlers/*.yml"))
        + sorted(ROOT.glob("*.yml"))
    )

    # First pass names the files reached through an include. Those carry their caller's
    # become, so scanning one standalone would report every task in it as undeclared.
    seen = set()
    for path in entries:
        scan(path, [], seen)

    found = []
    for path in entries:
        if str(path.relative_to(ROOT)) in seen:
            continue
        scan(path, found, set())
    return sorted(set(found))


def read_allowlist():
    if not ALLOWLIST.is_file():
        return set()
    lines = ALLOWLIST.read_text().splitlines()
    stripped = (line.strip() for line in lines)
    return {line for line in stripped if line and not line.startswith("#")}


def main():
    undeclared = {" -> ".join(entry) for entry in collect()}
    allowed = read_allowlist()

    new = sorted(undeclared - allowed)
    stale = sorted(allowed - undeclared)

    for entry in new:
        print(f"declares no identity: {entry}")
    for entry in stale:
        print(f"stale allowlist entry, delete it: {entry}")

    # Deduplicated: collect() scans every file twice, once to name the files reached
    # through an include and once to report, so each error is raised on both passes.
    for error in dict.fromkeys(ERRORS):
        print(error, file=sys.stderr)

    print(f"{len(undeclared)} undeclared, {len(allowed)} allowed, {len(new)} new, {len(stale)} stale")
    return 1 if new or stale or ERRORS else 0


if __name__ == "__main__":
    sys.exit(main())
