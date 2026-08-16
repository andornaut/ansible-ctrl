#!/usr/bin/env bash
# The checks CI gates on, defined once so a local run and a CI run cannot disagree.
# CI and `make lint` both call them all; the argument runs one on its own.
#
# Usage: tests/lint.sh [ansible-lint|syntax|shell|python]   (default: all)
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

# Not packaged for the distro, so a local run keeps it in a venv under .ansible/.
# CI pip-installs it instead, and this takes whichever is on PATH. Both install
# from requirements-dev.txt, so the version a local run rejects against is the
# version the gate rejects against.
readonly VENV=.ansible/lint-venv

# The directory every tool from requirements-dev.txt is run out of: ansible-lint, and the
# ansible-config and ansible-playbook the syntax check runs, which come from the pinned
# ansible-core beside it. Never bare names off PATH: the distro ships its own ansible-core,
# whose version no commit here names, so a syntax check taking that one rejects against a
# version the gate does not.
#
# ansible-lint is the marker of a requirements-dev.txt install, being the one tool the distro
# does not package: on PATH in CI, which pip-installs the file, and absent locally, where the
# venv is built instead.
#
# Sets LINT_BIN_DIR rather than printing it, so the two checks that need it resolve once.
LINT_BIN_DIR=""
require_lint_bin_dir() {
    local bin
    [[ -n ${LINT_BIN_DIR} ]] && return 0
    if bin=$(command -v ansible-lint); then
        LINT_BIN_DIR=$(dirname "${bin}")
        return 0
    fi
    [[ -x ${VENV}/bin/pip ]] || python3 -m venv "${VENV}" || return 1
    # Installed on every run, not only when the venv is missing: an existing venv keeps
    # whatever it was built with, so a pin bumped here would otherwise never reach it and
    # the local run would keep checking against a version no commit names.
    "${VENV}/bin/pip" install --quiet -r requirements-dev.txt || return 1
    LINT_BIN_DIR=${VENV}/bin
}

check_ansible_lint() {
    require_lint_bin_dir || return 1
    "${LINT_BIN_DIR}/ansible-lint"
}

# The real inventory is gitignored, so parse against tests/inventory.ini, which has
# a resolvable member for every targeted group.
#
# ansible.cfg first: an ini key ansible does not recognize is ignored in every other run,
# so a setting reads as made and is not. -t all covers the plugin options too, which is
# where the keys that do not match their option name live.
check_syntax() {
    local status=0 playbook
    require_lint_bin_dir || return 1
    echo "== ansible.cfg =="
    "${LINT_BIN_DIR}/ansible-config" validate -t all || status=1
    for playbook in *.yml; do
        [[ ${playbook} == requirements.yml ]] && continue
        echo "== ${playbook} =="
        "${LINT_BIN_DIR}/ansible-playbook" --syntax-check -i tests/inventory.ini "${playbook}" || status=1
    done
    return "${status}"
}

# Found by shebang rather than an enumerated list, so a new script needs no edit here. Line
# 1 only, so a #! deeper in another file is not mistaken for one. Every tracked file rather
# than roles/ alone, on the same reasoning as check_python: a script added elsewhere, this
# one included, is covered without anyone remembering to add it. Tracked, because
# ansible-galaxy installs collections into .ansible/, and third-party shell is not this
# repository's to lint.
#
# ShellCheck cannot parse Jinja2, so templates are rendered to a temporary copy first, named
# by flattened repo-relative path so a shared basename cannot overwrite. Everything else is
# checked where it lies, so the path ShellCheck reports is the one to go and edit.
check_shell() {
    local dir src first dest status
    local -a targets=()
    dir=$(mktemp -d) || return 1

    while IFS= read -r -d '' src; do
        [[ -f ${src} ]] || continue
        IFS= read -r first <"${src}" || true
        grep -qE '^#!.*\b(bash|sh)\b' <<<"${first}" || continue
        if [[ ${src} == */templates/* ]]; then
            dest="${dir}/${src//\//_}"
            dest="${dest%.j2}.sh"
            sed -E -e 's/\{\{[^}]*\}\}/PLACEHOLDER/g' -e 's/\{%[^%]*%\}//g' "${src}" >"${dest}"
            targets+=("${dest}")
        else
            targets+=("${src}")
        fi
    done < <(git ls-files -z)

    shellcheck "${targets[@]}"
    status=$?
    rm -rf "${dir}"
    return "${status}"
}

# ruff, the same version and settings the other Python repositories here run, so one gate
# governs Python everywhere. The whole tree rather than a list of paths, so a script added
# outside roles/ is covered without anyone remembering to add it: ruff.toml names the one
# per-file exception, and ruff reads its own excludes.
#
# A shebang-only script would need naming here, ruff discovering Python by extension; there
# are none today, and the roles copy every .py verbatim with no task parsing it, so without
# this a mistake ships and surfaces only when one is run.
check_python() {
    local status=0
    require_lint_bin_dir || return 1
    echo "== ruff check =="
    "${LINT_BIN_DIR}/ruff" check . || status=1
    echo "== ruff format =="
    "${LINT_BIN_DIR}/ruff" format --check . || status=1
    return "${status}"
}

main() {
    local checks check result status=0

    case "${1:-all}" in
    all) checks=(ansible-lint syntax shell python) ;;
    ansible-lint | syntax | shell | python) checks=("$1") ;;
    *)
        echo "usage: ${0} [ansible-lint|syntax|shell|python]" >&2
        return 2
        ;;
    esac

    for check in "${checks[@]}"; do
        echo "===== ${check} ====="
        "check_${check//-/_}"
        result=$?
        # Every check runs even after one fails: stopping at the first hides how
        # much else is broken, and one run should name everything that needs fixing.
        if ((result == 0)); then
            echo "----- ${check}: ok"
        else
            echo "----- ${check}: FAILED"
            status=1
        fi
    done
    return "${status}"
}

main "$@"
