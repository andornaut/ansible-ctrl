#!/bin/bash
# Runs as gamescope's child, where DISPLAY names gamescope's nested X server and
# WAYLAND_DISPLAY is unset. The game runs in a pressure-vessel sub-sandbox whose DISPLAY and
# WAYLAND_DISPLAY the flatpak portal resets to the host's after every environment option is
# applied, so the DISPLAY is carried in a variable of its own and a preloaded library
# restores both in each process that starts there.
#
# WORKAROUND: the sub-sandbox gets the portal's own environment, not the launcher's. Remove
# the carried DISPLAY and the preload once a flatpak the hosts run passes the caller's:
# https://github.com/flatpak/flatpak/issues/5278
set -euo pipefail

dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

export GAMESCOPE_CHILD_XDISPLAY="$DISPLAY"

# Left for ld.so to expand: $LIB is the multiarch library directory of the loading process's
# own class, so the one entry names the 64-bit build in a 64-bit process and the 32-bit build
# in a 32-bit one. pressure-vessel carries the token into the container.
export LD_PRELOAD="$dir/\${LIB}/libgamescope-display.so${LD_PRELOAD:+:$LD_PRELOAD}"

# WORKAROUND: umu-run empties LD_PRELOAD when either of these is `gamescope`, which gamescope
# sets XDG_CURRENT_DESKTOP to for its child. Nothing in the game container reads the host's
# values. Remove once umu stops clearing it:
# https://github.com/Open-Wine-Components/umu-launcher/pull/620
unset XDG_CURRENT_DESKTOP XDG_SESSION_DESKTOP

exec "$@"
