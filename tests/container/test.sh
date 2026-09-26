#!/usr/bin/env bash
# Runs tests/lint.sh, every check or the one named, inside a container: the unit tests
# execute code, so they never run on the host. The checkout is mounted read-only and copied
# into the container's own filesystem; nothing else from the host is mounted, the network
# is off, and the checks run as a uid that owns nothing on the host, with the checkout's
# group added so it can read what the group can.
#
# Usage: tests/container/test.sh [check]   (the arguments tests/lint.sh takes)
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 1

readonly IMAGE=ansible-ctrl-test

# The context is only what the Dockerfile copies, streamed as a tar, so an edit anywhere
# else in the tree keeps every cached layer.
tar -c tests/container/Dockerfile requirements-dev.txt requirements.yml package.json package-lock.json |
    docker build --quiet --tag "${IMAGE}" --file tests/container/Dockerfile - >/dev/null

# The file list comes from the host's git, which reads the user's global excludes as well as
# the repo's: agent state such as .codex/ is ignored only there, and may be unreadable here.
git ls-files -z --cached --others --exclude-standard |
    docker run --rm --interactive \
        --network none \
        --user 10001:10001 \
        --group-add "$(stat -c %g .)" \
        --cap-drop ALL \
        --security-opt no-new-privileges \
        --mount "type=bind,source=${PWD},target=/src,readonly" \
        "${IMAGE}" bash /src/tests/container/run.sh "$@"
