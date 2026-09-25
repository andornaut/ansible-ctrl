#!/usr/bin/env bash
# Applies a playbook to tests/check/inventory.yml's one host, the machine running this, then
# runs it again under --check --diff. The first run is what a fresh host gets from role
# defaults; the second catches a task that breaks under check mode on a converged host.
#
# Usage: tests/check.sh <playbook> [ansible-playbook arguments...]
#
# CI only: it configures the machine it runs on, becoming root through the runner's passwordless
# sudo.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <playbook> [ansible-playbook arguments...]" >&2
    exit 2
fi
playbook=$1
shift

# secrets_required=false: the stub host holds no credential and nothing is injected, so the
# pre_tasks assert in the playbooks that read one would stop the run before any role.
run() {
    ansible-playbook \
        --inventory tests/check/inventory.yml \
        --extra-vars secrets_required=false \
        "${playbook}.yml" \
        "$@"
}

echo "::group::Apply ${playbook}.yml"
run "$@"
echo "::endgroup::"
run --check --diff "$@"
