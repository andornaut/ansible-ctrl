#!/usr/bin/env bash
# Applies a playbook to tests/check/inventory.yml's one host, the machine running this: what a
# fresh host gets from role defaults. Tasks tagged `slow` are skipped, so a matrix entry fits
# in CI's five-minute budget.
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
ansible-playbook \
    --inventory tests/check/inventory.yml \
    --extra-vars secrets_required=false \
    --skip-tags slow \
    "${playbook}.yml" \
    "$@"
