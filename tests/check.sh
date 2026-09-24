#!/usr/bin/env bash
# Runs a playbook under --check --diff against tests/check/inventory.yml: one host, the
# machine running this, over the local connection, carrying role defaults and nothing more.
# It catches a task that breaks under check mode and a default that fails its own role's
# assert, before either reaches a real host.
#
# Usage: tests/check.sh <playbook> [ansible-playbook arguments...]
#
# CI only. A task marked check_mode: false still executes under --check, and with become
# those run as root on the machine running this. Every such task in the covered roles
# reads, or writes inside a directory ansible.builtin.tempfile made, but that is a property
# of the roles today rather than something this script enforces.
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
exec ansible-playbook \
    --inventory tests/check/inventory.yml \
    --check \
    --diff \
    --extra-vars secrets_required=false \
    "${playbook}.yml" \
    "$@"
