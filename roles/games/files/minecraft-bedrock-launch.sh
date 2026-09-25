#!/bin/bash
# Launch Minecraft Bedrock, or focus an existing window if already running.
#
# A desktop entry has no other channel, and BedrockOnLinux takes ten to fifteen seconds to
# show a window, so one notification is kept current through the launch: re-sent every few
# seconds for as long as something is being waited for, its body naming what that is, and
# closed the moment the game has a window. A launch that did not happen gets a longer banner.
# Every one is transient, so none is added to the message list: one left there stays until
# it is dismissed by hand, and a second run cannot replace it, the id reaching no further
# than the process that got it.
#
# Every decision is logged to $XDG_STATE_HOME/minecraft-bedrock-launch/minecraft.log (default
# ~/.local/state), since a desktop entry's stderr goes nowhere: the lock's state, what was
# found running, every change of the banner, what the nested display shows, and how `play`
# exited. Rotated by size.
set -uo pipefail

APP_ID=io.github.wyze3306.BedrockOnLinux
FLATPAK_CMD="/usr/bin/flatpak run --branch=master --arch=x86_64 --command=bedrock-on-linux $APP_ID"

# How long a click waits for the lock another launch holds. A launch keeps it until its
# window is up, so this is how long a second click sits behind a first one before giving up.
LOCK_WAIT_SECONDS=30
# How long the banner is kept up waiting for the game's window, and how often it is re-sent
# meanwhile. A launch with nothing on screen after this has failed some other way.
WINDOW_SECONDS=600
NOTIFY_REFRESH_SECONDS=3
# A window at least this many pixels on both sides is one the user can see. Everything else
# on gamescope's nested server is 1x1 bookkeeping, and a splash screen is well above it.
WINDOW_MIN_PIXELS=64
# The log is bounded: one launch writes a few dozen lines at most.
LOG_MAX_BYTES=1048576
LOG_BACKUPS=3

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/minecraft-bedrock-launch"
LOG_FILE="$STATE_DIR/minecraft.log"

setup_log() {
    mkdir -p "$STATE_DIR" 2>/dev/null || return
    local size i
    size=$(stat -c %s "$LOG_FILE" 2>/dev/null) || size=0
    [ "$size" -ge "$LOG_MAX_BYTES" ] || return
    for ((i = LOG_BACKUPS - 1; i >= 1; i--)); do
        [ -e "$LOG_FILE.$i" ] && mv -f "$LOG_FILE.$i" "$LOG_FILE.$((i + 1))"
    done
    mv -f "$LOG_FILE" "$LOG_FILE.1"
}

log() {
    echo "[minecraft-launch] $*" >&2
    echo "$(date '+%Y-%m-%d %H:%M:%S') [$$] $*" >>"$LOG_FILE" 2>/dev/null
}

# One notification, replaced in place as the launch moves on. keep() is called on every poll:
# the banner is re-sent at NOTIFY_REFRESH_SECONDS, shorter than its expiry, so it stays on
# screen for as long as the wait does, and at once when its text changes. Each change of
# text is logged, each re-send is not. The failure asks for the longer banner, being the one
# worth reading.
NOTIFY_ID=""
NOTIFY_CURRENT=""
NOTIFY_SENT_AT=0
notify() {
    local urgency=$1 summary=$2 body=${3:-} expire=8000
    [ "$urgency" = low ] || expire=20000
    if [ "$urgency|$summary|$body" != "$NOTIFY_CURRENT" ]; then
        log "notification: $summary: ${body:-(no body)}"
        NOTIFY_CURRENT="$urgency|$summary|$body"
    fi
    NOTIFY_SENT_AT=$EPOCHSECONDS
    local -a opts=(--print-id --app-name=Minecraft --icon=minecraft-bedrock --urgency="$urgency"
        --transient --expire-time="$expire")
    [ -n "$NOTIFY_ID" ] && opts+=(--replace-id="$NOTIFY_ID")
    NOTIFY_ID=$(notify-send "${opts[@]}" "$summary" "$body" 2>/dev/null) || true
}
keep() {
    local urgency=$1 summary=$2 body=${3:-}
    if [ "$urgency|$summary|$body" != "$NOTIFY_CURRENT" ] ||
        [ $((EPOCHSECONDS - NOTIFY_SENT_AT)) -ge "$NOTIFY_REFRESH_SECONDS" ]; then
        notify "$urgency" "$summary" "$body"
    fi
}
# Take the banner down now. notify-send cannot; the notification daemon's bus method can.
# A closed id is not replaced; the next banner is a new one.
notify_close() {
    [ -n "$NOTIFY_ID" ] || return 0
    if gdbus call --session --dest org.freedesktop.Notifications \
        --object-path /org/freedesktop/Notifications \
        --method org.freedesktop.Notifications.CloseNotification "$NOTIFY_ID" >/dev/null 2>&1; then
        log "notification closed"
    else
        log "CloseNotification failed for id $NOTIFY_ID"
    fi
    NOTIFY_ID=""
    NOTIFY_CURRENT=""
}

# An instance running the launcher (`gui`, which its own entry starts and whose PLAY button
# runs the game in-process), `play`, or the bare command. The game's own sub-sandbox and any
# helper instance carry the app ID too, and a leftover of those alone is not a running copy:
# it would send this to the focus branch with no window to focus. The child pid is the
# sandbox's bwrap, whose command line names what the instance runs. Sets RUNNING_GAME for a
# `play` or bare instance and RUNNING_GUI for a launcher. Only the first is known to be a
# game: a launcher with no game window may be idle or may be starting one from PLAY, and
# nothing on the host tells those apart before the game's window is up.
RUNNING_GAME=0
RUNNING_GUI=0
running_instance() {
    local app pid cmd
    RUNNING_GAME=0
    RUNNING_GUI=0
    while read -r app pid; do
        [ "$app" = "$APP_ID" ] || continue
        cmd=$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null) || continue
        case "$cmd" in
            *" -- bedrock-on-linux play "* | *" -- bedrock-on-linux ") RUNNING_GAME=1 ;;
            *" -- bedrock-on-linux gui "*) RUNNING_GUI=1 ;;
        esac
    done < <(flatpak ps --columns=application,child-pid)
    [ "$RUNNING_GAME" = 1 ] || [ "$RUNNING_GUI" = 1 ]
}

# The nested X display gamescope gave the game, named in the environment of the game's
# processes by the role's gamescope-child wrapper. The host reads it out of /proc, and it
# works on an X11 host and a Wayland one alike, unlike a search of the host display.
nested_display() {
    local environ display
    while IFS= read -r -d '' environ; do
        display=$(tr '\0' '\n' <"$environ" 2>/dev/null | sed -n 's/^GAMESCOPE_CHILD_XDISPLAY=//p' | head -1)
        if [ -n "$display" ]; then
            echo "$display"
            return 0
        fi
    done < <(grep -lzZ "^FLATPAK_ID=$APP_ID$" /proc/[0-9]*/environ 2>/dev/null)
    return 1
}

# The first window on that display big enough for the user to see and mapped. The listing
# carries each child's geometry but not whether it is mapped, so every child that is large
# enough is then asked for its own map state.
nested_window() {
    local display=$1 line id geometry width height
    while IFS= read -r line; do
        id=${line%% *}
        [[ $id == 0x* ]] || continue
        geometry=$(grep -oE '\b[0-9]+x[0-9]+[+-][0-9]+[+-][0-9]+' <<<"$line" | head -1)
        [ -n "$geometry" ] || continue
        width=${geometry%%x*}
        height=${geometry#*x}
        height=${height%%[+-]*}
        [ "$width" -ge "$WINDOW_MIN_PIXELS" ] && [ "$height" -ge "$WINDOW_MIN_PIXELS" ] || continue
        if xwininfo -display "$display" -id "$id" 2>/dev/null | grep -q IsViewable; then
            echo "$id ${line#* }"
            return 0
        fi
    done < <(xwininfo -display "$display" -root -children 2>/dev/null | sed -E 's/^\s+//')
    return 1
}

# By WM_CLASS, not the "Minecraft" title alone, which also matches Mutter's separate
# decoration frame window. Under gamescope on an X11 host the host sees gamescope's
# window, whose class every gamescope instance shares, so that match takes the title
# too. On a Wayland host gamescope's window is a native toplevel xdotool cannot see, so
# neither search finds it. This is the window to focus; whether the game has one is asked
# of the nested display instead, gamescope's host window being up before the game's is.
host_window() {
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

# Whether the game has a window the user can see: on gamescope's nested display where there
# is one, else on the host display, where a launch with no gamescope puts it.
game_window() {
    local display
    if display=$(nested_display); then
        nested_window "$display"
    else
        local w
        w=$(host_window)
        [ -n "$w" ] && echo "$w"
    fi
}

focus_window() {
    local w
    w=$(host_window)
    [ -n "$w" ] || return 1
    # Best-effort: on GNOME Wayland the compositor may treat the activate as an
    # attention hint rather than raising the window.
    log "focusing host window $w"
    xdotool windowactivate --sync "$w" 2>/dev/null
    xdotool windowfocus "$w" 2>/dev/null
    xdotool windowraise "$w" 2>/dev/null
}

setup_log
log "launching Minecraft (Bedrock): $APP_ID"

# One launch at a time, held from the click until the game has a window or the wait for one
# has ended. A desktop entry gives no launch feedback and the game takes ten to fifteen
# seconds to show a window, which makes a second click the ordinary case rather than the
# exceptional one, and two runs racing decide independently that nothing is running, then
# clear each other's GPU-session marker. Released by the kernel when this exits, so a run
# that is killed leaves nothing to clear. A click that lands on it while the holder's game
# has a window is told the game is running; one that lands during the launch waits.
LOCKED=0
if [ -n "${XDG_RUNTIME_DIR:-}" ]; then
    exec 9>>"$XDG_RUNTIME_DIR/minecraft-bedrock-launch.lock"
    if flock -n 9; then
        LOCKED=1
        log "lock acquired"
    else
        log "lock is held by another launch"
        if window=$(game_window); then
            log "its game has a window ($window); leaving it alone"
            notify low "Minecraft is already running"
            focus_window || true
            exit 0
        fi
        log "waiting up to ${LOCK_WAIT_SECONDS}s for it"
        deadline=$((EPOCHSECONDS + LOCK_WAIT_SECONDS))
        until flock -n 9; do
            if [ "$EPOCHSECONDS" -ge "$deadline" ]; then
                log "lock still held after ${LOCK_WAIT_SECONDS}s; giving up"
                notify normal "Minecraft did not start" "Another launch has held the lock for $LOCK_WAIT_SECONDS seconds."
                exit 1
            fi
            keep low "Launching Minecraft" "Another launch is in progress; waiting for it to finish."
            sleep 0.2
        done
        LOCKED=1
        log "lock acquired after the wait"
    fi
else
    log "no XDG_RUNTIME_DIR; launching without the concurrency guard"
fi
release_lock() {
    [ "$LOCKED" = 1 ] || return 0
    flock -u 9
    LOCKED=0
    log "lock released"
}

if running_instance; then
    log "a BedrockOnLinux instance is running"

    # A `play` outlives its game by a few seconds, so a click that follows the game's close
    # finds an instance and no window. Wait out that gap rather than doing nothing: the
    # window appears, or the instance ends and this launches.
    window=""
    for _ in $(seq 1 20); do
        window=$(game_window) && break
        running_instance || break
        sleep 0.5
    done
    if [ -n "$window" ]; then
        log "its game has a window ($window)"
        notify low "Minecraft is already running"
        # On a Wayland host gamescope's window is a native toplevel xdotool cannot see, so
        # there is nothing to focus and the banner is the whole answer.
        focus_window || log "no host window to focus"
        exit 0
    fi
    if running_instance; then
        if [ "$RUNNING_GAME" = 1 ]; then
            log "no window yet; the game may still be starting"
            notify normal "Minecraft is still starting" "Wait for its window."
        else
            log "the BedrockOnLinux launcher is open with no game window; it may be idle or starting the game"
            notify normal "Minecraft or its launcher is already open" "Switch to it, or close the BedrockOnLinux launcher to launch from here."
        fi
        exit 0
    fi
    log "the instance ended while waiting"
fi

log "no running BedrockOnLinux instance"

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
        log "clearing stale GPU-session lock: $marker"
        rm -f "$marker"
    fi
done

# `play` is the whole launch: it starts offline when no Microsoft account is linked, and
# reports a refused launch as a desktop notification, which is the only channel a desktop
# entry has. Signing in stays a launcher step, its device-code flow having nowhere to
# display from here.
#
# `9>&-` closes the lock descriptor in the child: a shell opens fd 9 inheritable, so a game
# process that outlives this script would otherwise keep the lock held and refuse every later
# launch. Run in the background so the window can be waited for while it runs; it blocks
# for the game's life, and its exit code is reported at the end.
notify low "Launching Minecraft" "Starting BedrockOnLinux."
$FLATPAK_CMD play 9>&- &
PLAY_PID=$!
log "started play as pid $PLAY_PID"

# Not `kill -0`: an exited child is a zombie until it is waited for, and a zombie answers.
play_running() {
    local state
    state=$(sed 's/.*) //' "/proc/$PLAY_PID/stat" 2>/dev/null | cut -d' ' -f1) || return 1
    [ -n "$state" ] && [ "$state" != Z ]
}

deadline=$((EPOCHSECONDS + WINDOW_SECONDS))
shown=0
exited_early=0
last_display=""
while [ "$EPOCHSECONDS" -lt "$deadline" ]; do
    if ! play_running; then
        log "play exited before a window appeared"
        exited_early=1
        break
    fi
    if display=$(nested_display) && [ "$display" != "$last_display" ]; then
        log "gamescope display $display found in the game's environment"
        last_display=$display
    fi
    if window=$(game_window); then
        log "the game has a window ($window)"
        notify_close
        shown=1
        break
    fi
    if running_instance; then
        keep low "Launching Minecraft" "Waiting for the game's window."
    else
        keep low "Launching Minecraft" "Starting BedrockOnLinux."
    fi
    sleep "$NOTIFY_REFRESH_SECONDS"
done
if [ "$shown" = 0 ] && play_running; then
    log "no window after ${WINDOW_SECONDS}s"
    notify normal "Minecraft did not start" "No window appeared in ten minutes."
fi
release_lock

wait "$PLAY_PID"
rc=$?
case "$rc" in
    0)
        log "play exited 0"
        # `play` exits 0 whatever became of the game, so a launch that showed nothing is a
        # failure it did not report. The launcher's own log has the reason; its tail is
        # copied here, where every other decision of the launch is.
        if [ "$exited_early" = 1 ]; then
            game_log="$HOME/.var/app/$APP_ID/data/bedrock-on-linux/logs/minecraft.log"
            log "the game's log, $game_log, ends:"
            tail -n 5 "$game_log" 2>/dev/null | while IFS= read -r line; do log "  $line"; done
            notify normal "Minecraft did not start" "BedrockOnLinux exited without showing a window. See $LOG_FILE."
            rc=1
        fi
        ;;
    # 128 + SIGTERM or SIGKILL: a later launch's teardown, or the user's own kill, not a
    # failure of this one.
    143 | 137) log "play was terminated (exit code $rc)" ; rc=0 ;;
    *)
        log "play exited $rc"
        notify normal "Minecraft did not start" "BedrockOnLinux exited with code $rc."
        ;;
esac
exit "$rc"
