#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
case "${1:-all}" in
    all) exec make check ;;
    static) exec make lint ;;
    ansible-lint|config|shell|python|identity|dispatch|markdown)
        PYTHON_IMAGE="python:$(<.python-version)"
        node_version=$(<.nvmrc)
        MARKDOWN_IMAGE="node:${node_version#v}"
        export PYTHON_IMAGE MARKDOWN_IMAGE
        exec tests/container/check-stock "$@"
        ;;
    *) printf 'Unknown check: %s\n' "$1" >&2; exit 2 ;;
esac
