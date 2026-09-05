#!/bin/bash
# The `gamescope` a game launcher's sandbox PATH finds first, granted by the role. Runs the
# VulkanLayer extension's binary with the game command prefixed by gamescope-child, which is
# what points the game at gamescope's own display rather than the host's: README.md.
set -euo pipefail

dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

opts=()
while (($#)); do
    if [[ $1 == -- ]]; then
        shift
        break
    fi
    opts+=("$1")
    shift
done

bin=/usr/lib/extensions/vulkan/gamescope/bin/gamescope

# Lutris reads `gamescope --help` for the options a version has, so an invocation that
# carries no command goes to the binary as is.
if (($# == 0)); then
    exec "$bin" "${opts[@]}"
fi

exec "$bin" "${opts[@]}" -- "$dir/gamescope-child" "$@"
