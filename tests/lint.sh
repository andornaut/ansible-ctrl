#!/usr/bin/env bash
# The checks CI gates on, defined once so a local run and a CI run cannot
# disagree. .github/workflows/lint.yml calls one check per job; `make lint` calls
# them all.
#
# Usage: tests/lint.sh [ansible-lint|syntax|shell|python]   (default: all)
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

# ansible-lint is not packaged for the distro, so a local run keeps it in a venv
# under .ansible/, which is gitignored and `make clean` removes. CI pip-installs
# it, so there it is already on PATH and no venv is built.
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

# The real inventory is gitignored, so parse against tests/inventory.ini, which
# supplies a resolvable member for every targeted group.
check_syntax() {
    local status=0 playbook
    for playbook in *.yml; do
        [[ ${playbook} == requirements.yml ]] && continue
        echo "== ${playbook} =="
        ansible-playbook --syntax-check -i tests/inventory.ini "${playbook}" || status=1
    done
    return "${status}"
}

# Every shell script under roles/, found by shebang rather than an enumerated
# list, so a new script in any role is covered without being added here. A script
# is a file under templates/ or files/ whose FIRST line is a bash/sh shebang,
# checked on line 1 only so a #! deeper in a non-script file is not mistaken for
# one. ShellCheck cannot parse Jinja2, so templates are rendered first by
# replacing {{ ... }} with a placeholder and stripping {% ... %}. The output name
# is the repo-relative path flattened, so scripts sharing a basename across roles
# cannot overwrite each other.
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

# Every Python file under roles/*/files/, found by extension or shebang for the
# same reason. A .py needs no shebang to be Python (Home Assistant's
# python_scripts are imported, not executed), and a script run from a shebang
# needs no extension. templates/ is not scanned: no role renders Python from
# Jinja2. The roles copy these files verbatim and no task parses them, so without
# this a syntax error ships and surfaces only when one is run.
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
        # Every check runs even after one fails, and each reports: a run that
        # stops at the first failure hides how much else is broken, and CI runs
        # these as four jobs that all report.
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
