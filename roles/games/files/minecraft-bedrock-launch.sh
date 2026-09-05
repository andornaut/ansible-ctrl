#!/bin/bash
# Launch Minecraft Bedrock, or focus an existing window if already running.
set -uo pipefail

APP_ID=io.github.wyze3306.BedrockOnLinux
FLATPAK_CMD="/usr/bin/flatpak run --branch=master --arch=x86_64 --command=bedrock-on-linux $APP_ID"

log() { echo "[minecraft-launch] $*"; }

# One notification, updated in place as the launch moves on: a desktop entry has no other
# channel, and BedrockOnLinux takes ten to fifteen seconds to show a window. Low-urgency
# ones are transient, so they leave the tray on their own; a failure stays.
NOTIFY_ID=""
notify() {
    local urgency=$1 summary=$2 body=${3:-}
    local -a opts=(--print-id --app-name=Minecraft --icon=minecraft-bedrock --urgency="$urgency")
    [ -n "$NOTIFY_ID" ] && opts+=(--replace-id="$NOTIFY_ID")
    [ "$urgency" = low ] && opts+=(--transient --expire-time=8000)
    NOTIFY_ID=$(notify-send "${opts[@]}" "$summary" "$body" 2>/dev/null) || true
}

# An instance running the launcher (`gui`, which its own entry starts and whose PLAY button
# runs the game in-process), `play`, or the bare command. The game's own sub-sandbox and any
# helper instance carry the app ID too, and a leftover of those alone is not a running copy:
# it would send this to the focus branch with no window to focus. The child pid is the
# sandbox's bwrap, whose command line names what the instance runs.
running_instance() {
    local app pid cmd
    while read -r app pid; do
        [ "$app" = "$APP_ID" ] || continue
        cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null) || continue
        case "$cmd" in
            *" -- bedrock-on-linux play "* | *" -- bedrock-on-linux gui "* | *" -- bedrock-on-linux ") return 0 ;;
        esac
    done < <(flatpak ps --columns=application,child-pid)
    return 1
}

# By WM_CLASS, not the "Minecraft" title alone, which also matches Mutter's separate
# decoration frame window. Under gamescope on an X11 host the host sees gamescope's
# window, whose class every gamescope instance shares, so that match takes the title
# too. On a Wayland host gamescope's window is a native toplevel xdotool cannot see, so
# neither search finds it.
minecraft_window() {
    local w
    w=$(xdotool search --onlyvisible --class minecraft.windows.exe 2>/dev/null | head -1)
    if [ -z "$w" ]; then
        for w in $(xdotool search --onlyvisible --class gamescope 2>/dev/null); do
            [ "$(xdotool getwindowname "$w" 2>/dev/null)" = Minecraft ] && break
            w=""
        done
    fi
    echo "$w"
}

log "Checking for a running BedrockOnLinux instance..."
if running_instance; then
    log "BedrockOnLinux is already running."

    # On a Wayland host gamescope's window is a native toplevel xdotool cannot see, so there
    # is nothing to find or focus and a live instance is the whole answer.
    if [ "${XDG_SESSION_TYPE:-}" = wayland ]; then
        notify low "Minecraft is already running"
        exit 0
    fi

    # A `play` outlives its game by a few seconds, so a click that follows the game's close
    # finds an instance and no window. Wait out that gap rather than doing nothing: the
    # window appears, or the instance ends and this launches.
    log "Searching for the Minecraft window..."
    WID=""
    for _ in $(seq 1 20); do
        WID=$(minecraft_window)
        [ -n "$WID" ] && break
        running_instance || break
        sleep 0.5
    done
    if [ -n "$WID" ]; then
        # Best-effort: on GNOME Wayland the compositor may treat the activate as an
        # attention hint rather than raising the window.
        log "Found window ID: $WID"
        notify low "Minecraft is already running"
        xdotool windowactivate --sync "$WID" 2>/dev/null
        xdotool windowfocus "$WID" 2>/dev/null
        xdotool windowraise "$WID" 2>/dev/null
        log "Done: window should be focused."
        exit 0
    fi
    if running_instance; then
        log "No window found via xdotool (game may still be starting)."
        notify normal "Minecraft is still starting" "Wait for its window."
        exit 0
    fi
    log "The instance ended while waiting."
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
notify low "Launching Minecraft" "The window takes a moment to appear."
$FLATPAK_CMD play
rc=$?
log "Play exited (exit code: $rc)."
if [ "$rc" -ne 0 ]; then
    notify normal "Minecraft did not start" "BedrockOnLinux exited with code $rc."
fi
