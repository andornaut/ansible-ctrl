#!/usr/bin/env bash
# The container side of tests/container/test.sh. Copies what git would commit from the
# read-only checkout at /src into /work, points the tooling tests/lint.sh would install at
# the copies baked into the image, and runs it.
set -euo pipefail

readonly SRC=/src WORK=/work

# Tracked and untracked files, not ignored ones: the set tests/lint.sh itself walks. A
# tracked file deleted in the work tree is still listed, and skipped here.
# The NUL-separated file list arrives on stdin from tests/container/test.sh.
while IFS= read -r -d '' path; do
        [[ -e ${SRC}/${path} || -L ${SRC}/${path} ]] && printf '%s\0' "${path}"
    done |
    tar -C "${SRC}" --null --files-from - -c | tar -C "${WORK}" -x

cd "${WORK}"
# A repository of its own, with nothing staged, so `git ls-files --others` lists the copy.
git init --quiet
printf '/node_modules\n' >>.git/info/exclude

mkdir -p .ansible
ln -s /opt/lint-venv .ansible/lint-venv
ln -s /opt/collections .ansible/collections
ln -s /opt/npm/node_modules node_modules

# The image installed node_modules from this lockfile; older than its install stamp, so the
# markdown check does not run npm ci, which would need the network.
if ! cmp -s package-lock.json /opt/npm/package-lock.json; then
    echo "package-lock.json differs from the image's: rebuild with tests/container/test.sh" >&2
    exit 1
fi
touch -d @0 package-lock.json

exec tests/lint.sh "$@"
