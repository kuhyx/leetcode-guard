#!/bin/bash
# ============================================================================
# deploy.sh -- the `- deploy:` line in CLAUDE.md: make origin/main live.
#
# The live deployment runs from the clone at ~/src/leetcode-guard (editable
# install into the system python's user site-packages). So a deploy is:
#   1. fast-forward that clone (refuse a dirty or diverged tree: concurrent
#      sessions edit it, so never stash, reset or merge);
#   2. run install.sh from it (package, units, coach relay, tray, MCP venv);
#   3. restart the two long-running units so they load the new code;
#   4. health-check, exiting non-zero and naming the first check that fails.
#
# Never starts or restarts leetcode-guard.service: that pops a lock window on
# the live display. It and the harvest oneshot pick the code up on their next
# timer run. Idempotent: a rerun with nothing to pull reinstalls and rechecks.
#
# Test seams: DEPLOY_LIVE_DIR, DEPLOY_PYTHON, DEPLOY_HEALTH_TIMEOUT.
# ============================================================================

set -euo pipefail

readonly LIVE_DIR="${DEPLOY_LIVE_DIR:-${HOME}/src/leetcode-guard}"
readonly SYSTEM_PYTHON="${DEPLOY_PYTHON:-/usr/bin/python3}"
readonly HEALTH_TIMEOUT="${DEPLOY_HEALTH_TIMEOUT:-20}"
readonly WEB_URL="http://127.0.0.1:8771/api/health"
readonly RELAY_URL="http://127.0.0.1:8777/coach/heartbeat"
readonly SERVICES=(leetcode-guard-web.service leetcode-coach-relay.service)
readonly TIMERS=(leetcode-guard.timer leetcode-guard-harvest.timer)

log() { printf 'deploy: %s\n' "$1" >&2; }
fail() { printf 'deploy: FAILED -- %s\n' "$1" >&2; exit 1; }

update_clone() {
    [[ -d "$LIVE_DIR/.git" ]] || fail "no git clone at $LIVE_DIR"
    if [[ -n "$(git -C "$LIVE_DIR" status --porcelain)" ]]; then
        git -C "$LIVE_DIR" status --short >&2
        fail "live clone $LIVE_DIR is dirty; commit or remove the edits, nothing was touched"
    fi
    git -C "$LIVE_DIR" pull --ff-only --quiet \
        || fail "pull in $LIVE_DIR is not a fast-forward; nothing was reset"
    log "live clone at $(git -C "$LIVE_DIR" log -1 --format='%h %s')"
}

restart_units() {
    systemctl --user restart "${SERVICES[@]}"
    systemctl --user enable "${TIMERS[@]}"
}

# Retries until the URL answers 2xx with a body matching $2, or the timeout.
probe_url() {
    local name="$1" url="$2" pattern="$3" body deadline=$((SECONDS + HEALTH_TIMEOUT))
    while :; do
        if body="$(curl -fsS -m 3 "$url" 2>/dev/null)" && [[ "$body" == *$pattern* ]]; then
            log "ok: $name answers on $url"
            return
        fi
        ((SECONDS < deadline)) || fail "health: $name does not answer on $url"
        sleep 1
    done
}

check_units() {
    local started_after="$1" unit stamp
    for unit in "${SERVICES[@]}" "${TIMERS[@]}"; do
        systemctl --user is-active --quiet "$unit" || fail "health: $unit is not active"
    done
    for unit in "${SERVICES[@]}"; do
        stamp="$(systemctl --user show "$unit" -p ActiveEnterTimestamp --timestamp=unix --value)"
        stamp="${stamp#@}"
        ((${stamp:-0} >= started_after)) \
            || fail "health: $unit not restarted by this deploy (running old code)"
    done
    for unit in "${TIMERS[@]}"; do
        systemctl --user show "$unit" -p NextElapseUSecRealtime -p NextElapseUSecMonotonic \
            | grep -qE '^NextElapseUSec[A-Za-z]+=.+' \
            || fail "health: $unit has no next run"
    done
    log "ok: services active and fresh, timers scheduled"
}

check_imports() {
    # The interpreter systemd runs must load the package from the live clone;
    # anything else means the units run code this deploy did not update.
    local where live
    where="$(cd / && "$SYSTEM_PYTHON" -P -c 'import leetcode_guard; print(leetcode_guard.__file__)')" \
        || fail "health: imports -- leetcode_guard does not import with $SYSTEM_PYTHON"
    live="$(cd "$LIVE_DIR" && pwd -P)"
    [[ "$where" == "$live"/* ]] \
        || fail "health: imports -- leetcode_guard loads from $where, not $live"
    log "ok: imports resolve to $live"
}

main() {
    local started
    started="$(date +%s)"
    update_clone
    "$LIVE_DIR/install.sh"
    restart_units
    check_units "$started"
    probe_url web "$WEB_URL" '"ok": true'
    probe_url relay "$RELAY_URL" '"beat"'
    check_imports
    log "health OK"
}

main "$@"
