#!/bin/bash
# ============================================================================
# deploy.sh -- the `- deploy:` line in CLAUDE.md: make origin/main live.
#
# The live deployment runs from the clone at ~/src/leetcode-guard (editable
# install into the system python's user site-packages). So a deploy is:
#   1. fast-forward that clone (refuse a diverged tree or a dirty deployed
#      path: concurrent sessions edit it, so never stash, reset or merge).
#      The Flutter app under app/ is not deployed by this script, so another
#      session's uncommitted edits there are pulled past and kept; git itself
#      refuses a pull that would overwrite one;
#   2. run install.sh from it (package, units, coach relay, tray, MCP venv).
#      Its two pip phases run side by side and are skipped while their stamps
#      match, which keeps a deploy under the 60 s action cap (2026-11-21: 68 s).
#      `deploy.sh --force` reinstalls both;
#   3. restart the two long-running units so they load the new code, and
#      keep a running lock out of swap (set-property, never a restart);
#   4. health-check, exiting non-zero and naming the first check that fails.
#
# Never starts or restarts leetcode-guard.service: that pops a lock window on
# the live display. It and the harvest oneshot pick the code up on their next
# timer run. Idempotent: a rerun with nothing to pull reinstalls and rechecks.
#
# Test seams: DEPLOY_LIVE_DIR, DEPLOY_PYTHON, DEPLOY_HEALTH_TIMEOUT,
# DEPLOY_CGROUP_ROOT.
# ============================================================================

set -euo pipefail

readonly LIVE_DIR="${DEPLOY_LIVE_DIR:-${HOME}/src/leetcode-guard}"
readonly SYSTEM_PYTHON="${DEPLOY_PYTHON:-/usr/bin/python3}"
readonly HEALTH_TIMEOUT="${DEPLOY_HEALTH_TIMEOUT:-20}"
readonly CGROUP_ROOT="${DEPLOY_CGROUP_ROOT:-/sys/fs/cgroup}"
readonly LOCK_UNIT=leetcode-guard.service
readonly WEB_URL="http://127.0.0.1:8771/api/health"
readonly RELAY_URL="http://127.0.0.1:8777/coach/heartbeat"
readonly SERVICES=(leetcode-guard-web.service leetcode-coach-relay.service)
readonly TIMERS=(leetcode-guard.timer leetcode-guard-harvest.timer)

log() { printf 'deploy: %s\n' "$1" >&2; }
fail() { printf 'deploy: FAILED -- %s\n' "$1" >&2; exit 1; }

update_clone() {
    [[ -d "$LIVE_DIR/.git" ]] || fail "no git clone at $LIVE_DIR"
    local dirty
    dirty="$(git -C "$LIVE_DIR" status --porcelain -- . ':(exclude)app')"
    if [[ -n "$dirty" ]]; then
        printf '%s\n' "$dirty" >&2
        fail "live clone $LIVE_DIR is dirty; commit or remove the edits, nothing was touched"
    fi
    git -C "$LIVE_DIR" pull --ff-only --quiet \
        || fail "pull in $LIVE_DIR is not a fast-forward (or would overwrite an app/ edit); nothing was reset"
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

# The unit pins MemorySwapMax=0 (a swapped idle lock stalls its Tk loop for
# over a second, 2026-11-22). A lock that is up keeps the cgroup it started
# with, so set the limit on it live; restarting it would re-lock the screen.
limit_lock_swap() {
    if systemctl --user is-active --quiet "$LOCK_UNIT"; then
        systemctl --user set-property --runtime "$LOCK_UNIT" MemorySwapMax=0
    fi
}

check_lock_swap() {
    local configured cgroup live
    configured="$(systemctl --user show "$LOCK_UNIT" -p MemorySwapMax --value)"
    [[ "$configured" == 0 ]] \
        || fail "health: $LOCK_UNIT has MemorySwapMax=$configured, not 0"
    if ! systemctl --user is-active --quiet "$LOCK_UNIT"; then
        log "ok: $LOCK_UNIT pins MemorySwapMax=0 (no lock running)"
        return
    fi
    cgroup="$(systemctl --user show "$LOCK_UNIT" -p ControlGroup --value)"
    live="$(cat "$CGROUP_ROOT$cgroup/memory.swap.max" 2>/dev/null || echo unreadable)"
    [[ "$live" == 0 ]] \
        || fail "health: running lock's memory.swap.max is $live, not 0"
    log "ok: lock is out of swap (memory.swap.max=0)"
}

check_imports() {
    # The interpreter systemd runs must load the package from the live clone;
    # anything else means the units run code this deploy did not update.
    local where live
    where="$(cd / && "$SYSTEM_PYTHON" -P -c 'import leetcode_guard, leetcode_guard._cli, gatelock; print(leetcode_guard.__file__)')" \
        || fail "health: imports -- leetcode_guard (or its _cli / gatelock) does not import with $SYSTEM_PYTHON"
    live="$(cd "$LIVE_DIR" && pwd -P)"
    [[ "$where" == "$live"/* ]] \
        || fail "health: imports -- leetcode_guard loads from $where, not $live"
    log "ok: imports resolve to $live"
}

main() {
    local started
    started="$(date +%s)"
    update_clone
    "$LIVE_DIR/install.sh" "$@"
    restart_units
    limit_lock_swap
    check_units "$started"
    check_lock_swap
    probe_url web "$WEB_URL" '"ok": true'
    probe_url relay "$RELAY_URL" '"beat"'
    check_imports
    log "health OK"
}

main "$@"
