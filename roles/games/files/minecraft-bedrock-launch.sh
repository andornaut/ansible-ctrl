#!/bin/bash
# Launch Minecraft Bedrock, or focus an existing window if already running.
set -uo pipefail

APP_ID=io.github.wyze3306.BedrockOnLinux
FLATPAK_CMD="/usr/bin/flatpak run --branch=master --arch=x86_64 --command=bedrock-on-linux $APP_ID"

log() { echo "[minecraft-launch] $*"; }

# Already running? Ask flatpak, which lists the app ID of every live sandbox instance. An exact
# match, so neither a same-named window nor an unrelated process sharing this script's PID can
# trigger a false positive and launch a second copy.
log "Checking for a running BedrockOnLinux instance..."
if flatpak ps --columns=application | grep -qx "$APP_ID"; then
    log "BedrockOnLinux is already running."

    # Focus its window. Match the Wine build's XWayland window by its WM_CLASS
    # (minecraft.windows.exe), not the "Minecraft" title: the title also matches Mutter's separate
    # server-side-decoration frame window. Best-effort only: on GNOME Wayland the compositor may
    # treat the activate as an attention hint rather than actually raising the window.
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

# BOL leaves a .gpu-launch-in-progress.json lock when a session is force-killed instead of exited
# cleanly, and refuses to launch while it exists. The flatpak ps check above already proved no
# instance is running, so a lock present here is stale: clear just it. Not BOL_ALLOW_UNSAFE_GPU,
# which would disable every gpu_safety check, including the RandR provider check the role vendors
# a host xrandr to satisfy.
marker="${XDG_DATA_HOME:-$HOME/.local/share}/bedrock-on-linux/.gpu-launch-in-progress.json"
if [ -e "$marker" ]; then
    log "Clearing stale GPU-session lock: $marker"
    rm -f "$marker"
fi

# Not running: login and launch
log "Running login..."
$FLATPAK_CMD login
login_status=$?
log "Login finished (exit code: $login_status)."

if [ "$login_status" -eq 0 ]; then
    log "Launching Minecraft..."
    $FLATPAK_CMD play
    log "Play exited (exit code: $?)."
else
    log "Login failed, skipping launch."
    exit "$login_status"
fi
