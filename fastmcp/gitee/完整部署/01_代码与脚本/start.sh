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

PYTHON_BIN="${G8_GATEWAY_PYTHON:-/opt/gitee-mcp-gateway/.venv/bin/python}"
NGROK_BIN="${G8_NGROK_BIN:-ngrok}"
GATEWAY_PORT="${G8_GATEWAY_PORT:-8765}"
START_TIMEOUT="${G8_START_TIMEOUT:-30}"
NGROK_SETTLE="${G8_NGROK_SETTLE_SECONDS:-2}"
NGROK_URL="https://mcp.example.com" # Placeholder: match gateway_server.py and the OAuth App.
NEW_GATEWAY=0
NEW_NGROK=0
FINISHED=0

rollback() {
    local rc=$?
    trap - EXIT HUP INT TERM
    if (( rc != 0 && FINISHED == 0 )); then
        event START_FAILED control "exit=$rc; rolling back processes started by this invocation"
        set +e
        (( NEW_NGROK == 0 )) || stop_service ngrok rollback
        (( NEW_GATEWAY == 0 )) || stop_service gateway rollback
    fi
    exit "$rc"
}
trap rollback EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

event START_REQUEST control "directory=$GATEWAY_DIR"
[[ "$GATEWAY_PORT" =~ ^[1-9][0-9]*$ ]] && (( GATEWAY_PORT <= 65535 )) || die 'Invalid G8_GATEWAY_PORT.'
[[ "$START_TIMEOUT" =~ ^[1-9][0-9]*$ ]] || die 'G8_START_TIMEOUT must be a positive integer.'
[[ "$NGROK_SETTLE" =~ ^[0-9]+([.][0-9]+)?$ ]] || die 'Invalid G8_NGROK_SETTLE_SECONDS.'
for required in nohup setsid; do
    command -v "$required" >/dev/null || die "Missing command: $required"
done
[[ -x "$PYTHON_BIN" && -f "$PYTHON_BIN" ]] || die "Python executable not found: $PYTHON_BIN"
NGROK_BIN="$(command -v "$NGROK_BIN")" || die 'ngrok executable not found; use the account with ngrok configured.'
[[ -f "$GATEWAY_DIR/gateway_server.py" ]] || die 'gateway_server.py is missing beside the scripts.'
[[ -f "$GATEWAY_DIR/.env" && ! -L "$GATEWAY_DIR/.env" && -r "$GATEWAY_DIR/.env" ]] || die 'A readable regular .env is required; the script never sources it.'
cd -- "$GATEWAY_DIR"

prepare_service() {
    local name="$1" rc
    if record_live "$name"; then
        event ALREADY_RUNNING "$name" "pid=$REC_PID"
        printf '%s already running (PID %s).\n' "$name" "$REC_PID"
        return 1
    else
        rc=$?
        (( rc != 2 )) || die "$name metadata cannot be verified; refusing another instance."
        archive_stale "$name"
        return 0
    fi
}

launch_service() {
    local name="$1" output pid state_tmp identity start pgid sid uid
    shift
    output="$(mktemp "$LOG_DIR/$name-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX.log")"
    printf '%s service=%s run=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$name" "$RUN_ID" >"$output"
    # Close FD 9: long-running children must not inherit the control lock.
    nohup setsid -- "$@" </dev/null >>"$output" 2>&1 9>&- &
    pid=$!
    # With job control disabled this child is not a group leader before setsid.
    # Still verify actual PID/PGID/SID rather than relying on that assumption.
    for _ in {1..30}; do
        if process_identity "$pid" && [[ "$LIVE_PGID" == "$pid" && "$LIVE_SID" == "$pid" ]]; then
            break
        fi
        sleep 0.05
    done
    if ! process_identity "$pid" || [[ "$LIVE_PGID" != "$pid" || "$LIVE_SID" != "$pid" || "$LIVE_UID" != "$RUN_UID" ]]; then
        event LAUNCH_FAILED "$name" "pid=$pid log=$output"
        die "$name did not establish a verified background process; see $output"
    fi
    start="$LIVE_START"; pgid="$LIVE_PGID"; sid="$LIVE_SID"; uid="$LIVE_UID"
    state_tmp="$(mktemp "$RUN_DIR/$name.pid.tmp.XXXXXX")"
    if ! printf '%s %s %s %s %s %s\n' "$pid" "$start" "$BOOT_ID" "$uid" "$pgid" "$sid" >"$state_tmp" ||
       ! mv -- "$state_tmp" "$RUN_DIR/$name.pid"; then
        if process_identity "$pid" && [[ "$LIVE_START" == "$start" && "$LIVE_PGID" == "$pid" && "$LIVE_SID" == "$pid" ]]; then
            kill -TERM -- "-$pid" 2>/dev/null || true
        fi
        die "$name metadata could not be saved; startup aborted."
    fi
    if [[ "$name" == gateway ]]; then NEW_GATEWAY=1; else NEW_NGROK=1; fi
    ln -sfn -- "$(basename -- "$output")" "$LOG_DIR/$name.latest.log"
    event STARTED "$name" "pid=$pid log=$output"
    printf '%s started (PID %s). Log: %s\n' "$name" "$pid" "$output"
}

port_available() {
    "$PYTHON_BIN" - "$GATEWAY_PORT" 9>&- <<'PY'
import socket, sys
with socket.socket() as probe:
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        probe.bind(("127.0.0.1", int(sys.argv[1])))
    except OSError:
        sys.exit(1)
PY
}

gateway_ready() {
    "$PYTHON_BIN" - "$GATEWAY_PORT" 9>&- <<'PY'
import sys, urllib.request, urllib.error
request = urllib.request.Request(
    "http://127.0.0.1:" + sys.argv[1] + "/mcp",
    headers={"Accept": "application/json, text/event-stream"},
)
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    with opener.open(request, timeout=1):
        sys.exit(1)
except urllib.error.HTTPError as exc:
    sys.exit(0 if exc.code == 401 else 1)
except Exception:
    sys.exit(1)
PY
}

if prepare_service gateway; then
    port_available || die "Port $GATEWAY_PORT is already occupied by an unmanaged process. Stop the old foreground gateway in its original terminal first."
    launch_service gateway "$PYTHON_BIN" -u "$GATEWAY_DIR/gateway_server.py"
fi
deadline=$(( $(date +%s) + START_TIMEOUT ))
while true; do
    record_live gateway || die 'Gateway exited during startup; see logs/gateway.latest.log.'
    if gateway_ready; then
        record_live gateway || die 'Gateway exited during its readiness check.'
        event READY gateway "127.0.0.1:$GATEWAY_PORT/mcp returned 401"
        break
    fi
    (( $(date +%s) < deadline )) || die 'Gateway readiness check timed out; see logs/gateway.latest.log.'
    sleep 0.2
done

if prepare_service ngrok; then
    launch_service ngrok "$NGROK_BIN" http "http://127.0.0.1:$GATEWAY_PORT" \
        "--url=$NGROK_URL" --inspect=false --log=stdout --log-format=json --log-level=info
    sleep "$NGROK_SETTLE"
    record_live ngrok || die 'ngrok exited during startup; see logs/ngrok.latest.log.'
fi
record_live gateway || die 'Gateway exited while ngrok was starting.'
record_live ngrok || die 'ngrok is no longer running.'
event START_COMPLETE control "gateway and ngrok processes running; inspect ngrok log for tunnel connection"
FINISHED=1
printf '\nBackground processes are running. SSH may now disconnect.\n'
printf 'Control history: %s/control.log\n' "$LOG_DIR"
printf 'Service output: %s/gateway.latest.log and %s/ngrok.latest.log\n' "$LOG_DIR" "$LOG_DIR"
printf 'A gateway restart requires reconnecting the ChatGPT plugin.\n'

