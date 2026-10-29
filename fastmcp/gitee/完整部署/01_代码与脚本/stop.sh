#!/usr/bin/env bash
# G8 gateway/ngrok process control for Ubuntu/Linux. No credentials are sourced.
set -Eeuo pipefail
set +m
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
GATEWAY_DIR="$(cd -- "${G8_GATEWAY_DIR:-$SCRIPT_DIR}" && pwd -P)"
RUN_DIR="$GATEWAY_DIR/run"
LOG_DIR="$GATEWAY_DIR/logs"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
RUN_UID="$(id -u)"
BOOT_ID="$(cat /proc/sys/kernel/random/boot_id)"
STOP_TIMEOUT="${G8_STOP_TIMEOUT:-8}"

[[ "$STOP_TIMEOUT" =~ ^[1-9][0-9]*$ ]] || { printf '%s\n' 'G8_STOP_TIMEOUT must be a positive integer.' >&2; exit 1; }
for required in flock stat date mktemp mv ln; do
    command -v "$required" >/dev/null || { printf 'Missing command: %s\n' "$required" >&2; exit 1; }
done
for directory in "$RUN_DIR" "$LOG_DIR"; do
    [[ ! -L "$directory" ]] || { printf 'Refusing symlink directory: %s\n' "$directory" >&2; exit 1; }
    mkdir -p -- "$directory"
    [[ "$(stat -c %u -- "$directory")" == "$RUN_UID" ]] || { printf 'Use the owner account for: %s\n' "$directory" >&2; exit 1; }
    chmod 700 -- "$directory"
done
for protected in "$RUN_DIR/control.lock" "$LOG_DIR/control.log"; do
    [[ ! -L "$protected" ]] || { printf 'Refusing symlink: %s\n' "$protected" >&2; exit 1; }
done
exec 9>>"$RUN_DIR/control.lock"
flock -w 60 9 || { printf '%s\n' 'Another start/stop operation is still running.' >&2; exit 1; }

event() {
    local action="$1" service="$2" detail="${3:-}"
    detail="${detail//$'\n'/ }"
    detail="${detail//$'\t'/ }"
    printf '%s\t%s\t%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$RUN_ID" "$action" "$service" "$detail" >>"$LOG_DIR/control.log"
    chmod 600 -- "$LOG_DIR/control.log"
}

die() {
    event ERROR control "$1"
    printf '%s\n' "$1" >&2
    exit 1
}

# /proc stat field 2 may contain spaces or ')': strip through the final ') '.
process_identity() {
    local pid="$1" line remainder
    local -a fields
    [[ "$pid" =~ ^[1-9][0-9]*$ && -r "/proc/$pid/stat" ]] || return 1
    IFS= read -r line <"/proc/$pid/stat" || return 1
    remainder="${line##*) }"
    read -r -a fields <<<"$remainder"
    (( ${#fields[@]} >= 20 )) || return 1
    [[ "${fields[0]}" != Z && "${fields[0]}" != X ]] || return 1
    LIVE_START="${fields[19]}"
    LIVE_PGID="${fields[2]}"
    LIVE_SID="${fields[3]}"
    LIVE_UID="$(stat -c %u -- "/proc/$pid" 2>/dev/null)" || return 1
}

# Return 0 for our live process, 1 for a stale record, 2 for invalid metadata.
record_live() {
    local name="$1" state="$RUN_DIR/$1.pid" extra=""
    [[ -e "$state" || -L "$state" ]] || return 1
    [[ -f "$state" && ! -L "$state" && "$(stat -c %u -- "$state")" == "$RUN_UID" ]] || return 2
    read -r REC_PID REC_START REC_BOOT REC_UID REC_PGID REC_SID extra <"$state" || return 2
    [[ -z "$extra" && "$REC_PID" =~ ^[1-9][0-9]*$ && "$REC_START" =~ ^[0-9]+$ &&
       "$REC_UID" =~ ^[0-9]+$ && "$REC_PGID" == "$REC_PID" && "$REC_SID" == "$REC_PID" &&
       "$REC_BOOT" =~ ^[0-9a-f-]+$ ]] || return 2
    [[ "$REC_BOOT" == "$BOOT_ID" && "$REC_UID" == "$RUN_UID" ]] || return 1
    process_identity "$REC_PID" || return 1
    [[ "$LIVE_START" == "$REC_START" && "$LIVE_UID" == "$REC_UID" &&
       "$LIVE_PGID" == "$REC_PGID" && "$LIVE_SID" == "$REC_SID" ]] || return 1
}

archive_stale() {
    local name="$1"
    [[ -e "$RUN_DIR/$name.pid" ]] || return 0
    mv -- "$RUN_DIR/$name.pid" "$RUN_DIR/$name.pid.stale.$RUN_ID"
    event STALE_RECORD "$name" 'No signal sent; previous metadata archived.'
}

stop_service() {
    local name="$1" reason="${2:-requested}" rc pid deadline
    if [[ ! -e "$RUN_DIR/$name.pid" && ! -L "$RUN_DIR/$name.pid" ]]; then
        event ALREADY_STOPPED "$name" "$reason"
        printf '%s already stopped.\n' "$name"
        return 0
    fi
    if record_live "$name"; then
        pid="$REC_PID"
    else
        rc=$?
        if (( rc == 2 )); then
            event REFUSED_STOP "$name" 'Invalid metadata; no signal sent.'
            printf '%s metadata cannot be verified; no process was stopped.\n' "$name" >&2
            return 1
        fi
        archive_stale "$name"
        printf '%s has no matching live process.\n' "$name"
        return 0
    fi
    # Re-check directly before every signal; only use the verified private group.
    if record_live "$name"; then
        event STOP_TERM "$name" "pid=$pid reason=$reason"
        kill -TERM -- "-$pid" 2>/dev/null || true
    fi
    deadline=$(( $(date +%s) + STOP_TIMEOUT ))
    while record_live "$name"; do
        if (( $(date +%s) >= deadline )); then
            if record_live "$name"; then
                event STOP_KILL "$name" "pid=$pid reason=$reason"
                kill -KILL -- "-$pid" 2>/dev/null || true
            fi
            break
        fi
        sleep 0.2
    done
    for _ in {1..20}; do
        if ! record_live "$name"; then
            rm -f -- "$RUN_DIR/$name.pid"
            event STOPPED "$name" "pid=$pid reason=$reason"
            printf '%s stopped (PID %s).\n' "$name" "$pid"
            return 0
        fi
        sleep 0.1
    done
    event STOP_FAILED "$name" "pid=$pid metadata retained"
    printf '%s did not stop; metadata retained.\n' "$name" >&2
    return 1
}

event STOP_REQUEST control "directory=$GATEWAY_DIR"
STOP_FAILED=0
# Stop public forwarding first, then the gateway. Never use global pkill.
stop_service ngrok requested || STOP_FAILED=1
stop_service gateway requested || STOP_FAILED=1
if (( STOP_FAILED != 0 )); then
    event STOP_INCOMPLETE control 'Some process metadata could not be verified or stopped.'
    exit 1
fi
event STOP_COMPLETE control 'Managed services stopped; logs retained.'
printf '\nManaged services stopped. Logs retained at %s\n' "$LOG_DIR"

