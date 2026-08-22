#!/usr/bin/env bash
# Keep adb reachable on Android TVs whose boot receiver the OEM prunes.
#
# Two jobs per TV, in order:
#   1. Reclaim adb. adb-auto-enable enables wireless debugging at boot, which
#      binds adbd to a random ephemeral port; find it and issue tcpip:<port> so
#      the port is fixed and Home Assistant's probe can find it.
#   2. Arm the next boot. The set re-disables the app's BootReceiver after every
#      boot, and a component of a non-test-only app cannot be re-enabled from a
#      shell ("Shell cannot change component state"), nor by `install -r`, which
#      preserves the disabled state.
#
# A build that repairs its own receiver on service start only needs launching,
# and keeps its adb key. Otherwise the app is reinstalled, which loses that key
# and any pairing made to it, so the launch is always tried first.
#
# A TV that is off, asleep or otherwise unreachable is an ordinary outcome and
# leaves the exit status alone: these run on a timer, and a set that is off for a
# week would otherwise report a failed unit every few minutes. Only work that was
# started and did not finish fails.
set -uo pipefail

HOSTS=${TV_ADB_HOSTS:?TV_ADB_HOSTS is required}
PORT=${TV_ADB_PORT:-5555}
PKG=${TV_ADB_PACKAGE:-com.tpn.adbautoenable}
APK=${TV_ADB_APK:?TV_ADB_APK is required}
UI_PORT=${TV_ADB_UI_PORT:-9093}

say() { printf '%s: %s\n' "$1" "$2"; }

# Three tries, not one: a single packet with a one second deadline drops often
# enough during boot to mislabel a set that is present, and a skipped run is the
# one thing standing between a pruned receiver and an adb that needs a person to
# get back.
reachable() { ping -c3 -W1 -i0.3 "$1" >/dev/null 2>&1; }

online() { adb -s "$1:$PORT" shell true >/dev/null 2>&1; }

# Drop stale transports for one host: a port left "offline" by an earlier scan
# makes adb connect report success without a usable device.
forget() {
    adb devices | awk -v h="$1" '$1 ~ "^"h":" {print $1}' |
        while read -r t; do adb disconnect "$t" >/dev/null 2>&1; done
}

# The app discovers adbd's port itself and publishes it, so ask before scanning:
# an answer here turns a 28000-port sweep into one connect. Empty when the app is
# not running, has not looked yet, or reports -1, which is what the scan is for.
published_port() {
    curl -s -m 5 "http://$1:$UI_PORT/api/status" 2>/dev/null |
        grep -o '"currentPort":[[:space:]]*[0-9-]*' |
        grep -o '[0-9-]*$' | grep -E '^[0-9]+$'
}

# 0 switched, 3 the set went away mid-switch, 2 it stayed up and the switch did
# not take. Telling those apart matters: a reboot landing inside a run would
# otherwise be reported as a failure, and these run on a timer.
switch_to_fixed_port() {
    local host=$1 p=$2
    say "$host" "adbd on $p, switching to $PORT"
    adb -s "$host:$p" tcpip "$PORT" >/dev/null 2>&1
    sleep 5
    adb disconnect "$host:$p" >/dev/null 2>&1
    adb connect "$host:$PORT" >/dev/null 2>&1
    online "$host" && return 0
    reachable "$host" || return 3
    return 2
}

# 0 adb usable, 1 no adb port anywhere, plus switch_to_fixed_port's codes.
reclaim() {
    local host=$1 p
    forget "$host"
    adb connect "$host:$PORT" >/dev/null 2>&1
    online "$host" && return 0
    adb disconnect "$host:$PORT" >/dev/null 2>&1

    p=$(published_port "$host")
    if [[ -n $p && $p != "$PORT" ]]; then
        adb connect "$host:$p" >/dev/null 2>&1
        if adb -s "$host:$p" shell true >/dev/null 2>&1; then
            switch_to_fixed_port "$host" "$p"
            return $?
        fi
        adb disconnect "$host:$p" >/dev/null 2>&1
    fi

    for p in $(nmap -Pn -T4 -p32768-61000 --open "$host" 2>/dev/null |
               awk -F/ '/^[0-9]+\/tcp/ {print $1}'); do
        [[ $p == "$PORT" ]] && continue
        adb connect "$host:$p" >/dev/null 2>&1
        # Whether the transport serves a shell is the only trustworthy test: adb
        # connect reports success for ports that never complete the handshake.
        if adb -s "$host:$p" shell true >/dev/null 2>&1; then
            switch_to_fixed_port "$host" "$p"
            return $?
        fi
        adb disconnect "$host:$p" >/dev/null 2>&1
    done
    return 1
}

package_installed() {
    adb -s "$1:$PORT" shell "pm list packages $PKG" 2>/dev/null |
        tr -d '\r' | grep -qx "package:$PKG"
}

# Read the resolution set rather than the disabled list: being dispatched to is
# the property that matters, and a set disabling several components prints them
# as a block that a fixed-size read of the dumpsys output would misjudge.
receiver_armed() {
    adb -s "$1:$PORT" shell \
        'pm query-receivers --components -a android.intent.action.BOOT_COMPLETED' 2>/dev/null |
        tr -d '\r' | grep -q "^$PKG/"
}

# No uninstall here, so a failed install leaves whatever was there. Callers that
# must replace the app uninstall first and rely on the absent-package branch of
# the main loop to install it on a later run if this fails.
install_app() {
    local host=$1
    adb -s "$host:$PORT" install "$APK" >/dev/null 2>&1 || return 1
    adb -s "$host:$PORT" shell "pm grant $PKG android.permission.WRITE_SECURE_SETTINGS" >/dev/null 2>&1
    # A freshly installed app sits in the stopped state, and stopped apps are not
    # sent broadcasts, so it has to be launched once to arm the next boot.
    adb -s "$host:$PORT" shell "am start -n $PKG/.MainActivity" >/dev/null 2>&1
    sleep 3
    receiver_armed "$host"
}

arm_next_boot() {
    local host=$1
    adb -s "$host:$PORT" shell "am start -n $PKG/.MainActivity" >/dev/null 2>&1
    sleep 3
    if receiver_armed "$host"; then
        say "$host" "BootReceiver restored by launching the app"
        return 0
    fi

    say "$host" "launching did not restore BootReceiver, reinstalling"
    adb -s "$host:$PORT" uninstall "$PKG" >/dev/null 2>&1
    if install_app "$host"; then
        say "$host" "BootReceiver restored by reinstalling the app"
        return 0
    fi
    say "$host" "reinstall failed and the app may now be absent; the next run installs it"
    return 1
}

status=0
for host in $HOSTS; do
    if ! reachable "$host"; then
        say "$host" "unreachable, nothing to do"
        continue
    fi

    reclaim "$host"
    case $? in
        0) ;;
        2)
            say "$host" "tcpip $PORT did not take"
            status=1
            continue
            ;;
        3)
            say "$host" "went away mid-switch, will retry next run"
            continue
            ;;
        *)
            # Distinct from unreachable on purpose: the set answered, so this is
            # the state nothing here can repair, because reaching the app needs
            # the adb that is missing. Not a unit failure, because it is also the
            # normal state for the five minutes a boot takes to reach the app.
            say "$host" "reachable but no adb port found; the app has not started"
            continue
            ;;
    esac

    if ! package_installed "$host"; then
        say "$host" "app is not installed, installing it"
        install_app "$host" || { say "$host" "install failed"; status=1; }
    elif ! receiver_armed "$host"; then
        arm_next_boot "$host" || status=1
    fi
done
exit "$status"
