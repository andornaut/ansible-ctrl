#!/bin/bash
# Launch Minecraft Bedrock, or focus an existing window if already running.
set -uo pipefail

APP_ID=io.github.wyze3306.BedrockOnLinux
FLATPAK_CMD="/usr/bin/flatpak run --branch=master --arch=x86_64 --command=bedrock-on-linux $APP_ID"

log() { echo "[minecraft-launch] $*"; }

# flatpak lists the app ID of every live sandbox instance. Matched exactly, so nothing
# else can read as a running copy and cause a second launch.
log "Checking for a running BedrockOnLinux instance..."
if flatpak ps --columns=application | grep -qx "$APP_ID"; then
    log "BedrockOnLinux is already running."

    # By WM_CLASS, not the "Minecraft" title, which also matches Mutter's separate
    # decoration frame window. Best-effort: on GNOME Wayland the compositor may treat
    # the activate as an attention hint rather than raising the window.
    log "Searching for the Minecraft window..."
    WID=$(xdotool search --onlyvisible --class minecraft.windows.exe 2>/dev/null | head -1)
    if [ -n "$WID" ]; then
        log "Found window ID: $WID"
        xdotool windowactivate --sync "$WID" 2>/dev/null
        xdotool windowfocus "$WID" 2>/dev/null
        xdotool windowraise "$WID" 2>/dev/null
        log "Done: window should be focused."
    else
        log "No window found via xdotool (game may still be starting)."
    fi
    exit 0
fi

log "No running BedrockOnLinux instance detected."

# A force-killed session leaves this lock behind and BOL refuses to launch while it exists.
# The check above proved nothing is running, so it is stale. Cleared rather than setting
# BOL_ALLOW_UNSAFE_GPU, which would disable every gpu_safety check, including the RandR one
# the role vendors a host xrandr to satisfy.
#
# The launcher writes it under its data directory, which is the flatpak's own XDG data home.
# The legacy path is cleared too: BOL copies that directory forward on its first 2.1.4 run,
# so a launcher that has not been opened since the update still writes to the old one. This
# script runs on the host, where XDG_DATA_HOME is the session's, not the sandbox's.
for marker in \
    "$HOME/.var/app/$APP_ID/data/bedrock-on-linux/.gpu-launch-in-progress.json" \
    "${XDG_DATA_HOME:-$HOME/.local/share}/bedrock-on-linux/.gpu-launch-in-progress.json"; do
    if [ -e "$marker" ]; then
        log "Clearing stale GPU-session lock: $marker"
        rm -f "$marker"
    fi
done

# `play` is the whole launch: it starts offline when no Microsoft account is linked, and
# reports a refused launch as a desktop notification, which is the only channel a desktop
# entry has. Signing in stays a launcher step, its device-code flow having nowhere to
# display from here.
log "Launching Minecraft..."
$FLATPAK_CMD play
log "Play exited (exit code: $?)."
