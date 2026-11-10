#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
if (( $# )); then
    case "$1" in
        static) exec make lint ;;
        all) exec make check ;;
        ansible-lint|config|shell|python|identity|dispatch|markdown)
            export CHECK_TASKS='lint test'
            export COMMAND="tests/lint.sh $1"
            exec tests/container/run command
            ;;
        *) printf 'Unknown check: %s\n' "$1" >&2; exit 2 ;;
    esac
fi
exec make check
