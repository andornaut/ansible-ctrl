#!/usr/bin/env python3
"""Print the check job's matrix, reduced to the entries whose paths changed.

Usage:
  tests/check_matrix.py <base-sha> <head-sha>

Writes `matrix=<json>` and `any=<true|false>` lines for $GITHUB_OUTPUT. The workflow passes
a pull request's base, or for a push the last commit a push run passed on. An empty,
all-zero or unknown base (no passing run yet, workflow_dispatch, a commit not fetched) selects
every entry, as does a change to any path in SHARED.
"""

import json
import subprocess
import sys

# What every entry reads: the shared task files in base, the credential check, the
# harness itself. A path ending in / is a directory prefix.
SHARED = (
    ".github/workflows/test.yml",
    ".python-version",
    "ansible.cfg",
    "requirements.yml",
    "requirements-dev.txt",
    "roles/base/tasks/get_latest_release.yml",
    "roles/base/tasks/require_kernel_headers.yml",
    "roles/base/tasks/require_tools.yml",
    "tasks/",
    "tests/check.sh",
    "tests/check/",
    "tests/check_matrix.py",
    "vars_plugins/",
)

# The toolchains the tiling builds require, which a host has from the dev role.
TILING_PREPARE = (
    "ansible-playbook --inventory tests/check/inventory.yml --extra-vars secrets_required=false dev.yml --tags go,rust"
)
# What that prepare step runs of the dev role.
TILING_PREPARE_PATHS = (
    "dev.yml",
    "roles/dev/defaults/",
    "roles/dev/tasks/go.yml",
    "roles/dev/tasks/main.yml",
    "roles/dev/tasks/rust.yml",
    "roles/dev/vars/",
)
# The Docker SDK the role requires. The runner ships Docker without it, and a host's first
# run applies the docker role ahead of this playbook.
DOCKER_SDK = "sudo apt-get update && sudo apt-get install --yes --no-install-recommends python3-docker"

MATRIX = (
    {"name": "base", "playbook": "base", "paths": ("base.yml", "roles/base/")},
    # One entry per desktop_environment: each selects different tasks in desktop and a
    # different window manager role.
    {"name": "desktop gnome", "playbook": "desktop", "paths": ("desktop.yml", "roles/desktop/")},
    {
        "name": "desktop niri",
        "playbook": "desktop",
        # A tiling host needs exactly one display manager; the two entries cover both.
        "args": "--extra-vars desktop_environment=niri --extra-vars desktop_install_lemurs=true",
        "prepare": TILING_PREPARE,
        "paths": ("desktop.yml", "roles/desktop/", "roles/niri/", *TILING_PREPARE_PATHS),
    },
    {
        "name": "desktop bspwm",
        "playbook": "desktop",
        "args": "--extra-vars desktop_environment=bspwm --extra-vars desktop_install_ly=true",
        "prepare": TILING_PREPARE,
        "paths": ("desktop.yml", "roles/desktop/", "roles/bspwm/", *TILING_PREPARE_PATHS),
    },
    {"name": "dev", "playbook": "dev", "paths": ("dev.yml", "roles/dev/")},
    {"name": "docker", "playbook": "docker", "paths": ("docker.yml", "roles/docker/")},
    {
        "name": "games",
        "playbook": "games",
        # The ROM library the role asserts is mounted, at the path the stub host_vars name.
        # The role reads it and never creates it.
        "prepare": (
            "mkdir -p /tmp/ansible-check/library/_BIOS/retroarch-system-folder /tmp/ansible-check/library/_Thumbnails"
        ),
        "paths": ("games.yml", "roles/games/"),
    },
    {"name": "hobbies", "playbook": "hobbies", "paths": ("hobbies.yml", "roles/hobbies/")},
    {
        "name": "homeautomation",
        "playbook": "homeautomation",
        # The Docker SDK, then the configuration.yaml an operator writes after Home
        # Assistant's first start, carrying the frontend include the role asserts.
        "prepare": (
            f"{DOCKER_SDK} &&"
            " sudo mkdir -p /var/docker-volumes/homeautomation/homeassistant/config &&"
            " printf 'default_config:\\nfrontend: !include frontend.yaml\\n' |"
            " sudo tee /var/docker-volumes/homeautomation/homeassistant/config/configuration.yaml >/dev/null"
        ),
        "paths": ("homeautomation.yml", "roles/homeautomation/"),
    },
    {"name": "msmtp", "playbook": "msmtp", "paths": ("msmtp.yml", "roles/msmtp/")},
    {
        "name": "webservers",
        "playbook": "webservers",
        "prepare": DOCKER_SDK,
        "paths": ("webservers.yml", "roles/letsencrypt_nginx/"),
    },
)


# The playbooks no entry applies: they need a second host, hardware, a router or the
# broker's own store, none of which the runner has.
NOT_COVERED = ("faramir", "nas", "router", "rsnapshot", "torrent", "upgrade")


def touches(paths: tuple[str, ...], changed: list[str]) -> bool:
    return any(f == p or (p.endswith("/") and f.startswith(p)) for f in changed for p in paths)


def select(changed: list[str] | None) -> list[dict]:
    """The entries to run: every one when changed is None or touches SHARED."""
    entries = [{k: v for k, v in e.items() if k != "paths"} for e in MATRIX]
    if changed is None or touches(SHARED, changed):
        return entries
    return [entry for entry, e in zip(entries, MATRIX, strict=True) if touches(e["paths"], changed)]


def changed_files(base: str, head: str) -> list[str] | None:
    """Files changed from base to head, or None when base names no commit here."""
    if not base.strip("0"):
        return None
    diff = subprocess.run(
        ["git", "diff", "--no-renames", "--name-only", base, head], capture_output=True, text=True, check=False
    )
    return diff.stdout.splitlines() if diff.returncode == 0 else None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    entries = select(changed_files(*argv))
    print(f"matrix={json.dumps({'include': entries})}")
    print(f"any={'true' if entries else 'false'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
