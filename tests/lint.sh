#!/usr/bin/env bash
# The checks CI gates on, defined once so a local run and a CI run cannot disagree.
# The workflow calls one check per job; `make lint` calls them all.
#
# Usage: tests/lint.sh [ansible-lint|syntax|shell|python]   (default: all)
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

# Not packaged for the distro, so a local run keeps it in a venv under .ansible/.
# CI pip-installs it instead, and this takes whichever is on PATH.
readonly VENV=.ansible/lint-venv

check_ansible_lint() {
    local bin
    if ! bin=$(command -v ansible-lint); then
        if [[ ! -x ${VENV}/bin/ansible-lint ]]; then
            python3 -m venv "${VENV}" || return 1
            "${VENV}/bin/pip" install --quiet ansible-lint || return 1
        fi
        bin=${VENV}/bin/ansible-lint
    fi
    "${bin}"
}

# The real inventory is gitignored, so parse against tests/inventory.ini, which has
# a resolvable member for every targeted group.
check_syntax() {
    local status=0 playbook
    for playbook in *.yml; do
        [[ ${playbook} == requirements.yml ]] && continue
        echo "== ${playbook} =="
        ansible-playbook --syntax-check -i tests/inventory.ini "${playbook}" || status=1
    done
    return "${status}"
}

# Found by shebang rather than an enumerated list, so a new script needs no edit here. Line
# 1 only, so a #! deeper in another file is not mistaken for one. ShellCheck cannot parse
# Jinja2, so templates are rendered first, named by flattened repo-relative path so a shared
# basename cannot overwrite.
check_shell() {
    local dir src first dest status
    dir=$(mktemp -d) || return 1

    while IFS= read -r src; do
        IFS= read -r first <"${src}" || true
        grep -qE '^#!.*\b(bash|sh)\b' <<<"${first}" || continue
        dest="${dir}/${src//\//_}"
        dest="${dest%.j2}.sh"
        if [[ ${src} == */templates/* ]]; then
            sed -E -e 's/\{\{[^}]*\}\}/PLACEHOLDER/g' -e 's/\{%[^%]*%\}//g' "${src}" >"${dest}"
        else
            cp "${src}" "${dest}"
        fi
    done < <(find roles/ -type f \( -path '*/templates/*' -o -path '*/files/*' \))

    shellcheck "${dir}"/*.sh
    status=$?
    rm -rf "${dir}"
    return "${status}"
}

# By extension or shebang, for the same reason: a .py needs no shebang to be Python, and a
# script run from one needs no extension. templates/ is not scanned, no role rendering
# Python from Jinja2. The roles copy these verbatim and no task parses them, so without this
# a syntax error ships and surfaces only when one is run.
check_python() {
    local status=0 src first
    while IFS= read -r src; do
        case "${src}" in
        *.py) ;;
        *)
            IFS= read -r first <"${src}" || true
            grep -qE '^#!.*\bpython3?\b' <<<"${first}" || continue
            ;;
        esac
        echo "== ${src} =="
        python3 -c 'import ast, sys; ast.parse(open(sys.argv[1]).read(), sys.argv[1])' "${src}" ||
            status=1
    done < <(find roles/ -type f -path '*/files/*')
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
        # much else is broken, and CI runs these as four jobs that all report.
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
