#!/bin/bash
# ============================================================================
# screenshot_lock.sh -- run the lock on an Xvfb display and keep the best frame.
#
# One `import -window root` is not a screenshot: fired before the surfaces
# paint it returns the overrideredirect backdrop, a uniformly charcoal image
# that looks exactly like an empty lock screen (two of three captures on
# 2026-08-09). `-window <id>` does not help -- the surface reports its full
# geometry before drawing anything. So this samples the whole window repeatedly
# and keeps the largest file; a blank frame is ~400 bytes, a painted one ~90 KB,
# and the sizes are never close.
#
# Usage: scripts/screenshot_lock.sh [OUT.png] [-- <python -m leetcode_guard args>]
#   DISPLAY   the Xvfb display to use (default :81); start it yourself with
#             `Xvfb :81 -screen 0 1600x1200x24 &`
#   SAMPLES   how many frames to try (default 90, one per ~second; a cold pool
#             fetch alone is ~40 pages at 0.5 s before anything paints)
# Kills the lock by PID when done -- never `pkill -f leetcode_guard`, it matches
# the shell running it.
# ============================================================================

set -euo pipefail

readonly DISPLAY="${DISPLAY:-:81}"
readonly SAMPLES="${SAMPLES:-90}"
OUT="/tmp/lock.png"
if [[ $# -gt 0 && "$1" != "--" ]]; then
    OUT="$1"
    shift
fi
[[ "${1:-}" == "--" ]] && shift
readonly OUT

TRY="$(mktemp --suffix=.png)"
SHOT=""
cleanup() {
    rm -f "$TRY"
    if [[ -n "$SHOT" ]] && kill -0 "$SHOT" 2>/dev/null; then
        kill "$SHOT"
    fi
}
trap cleanup EXIT

export DISPLAY
python3 -m leetcode_guard "$@" &
SHOT=$!

BEST=0
for _ in $(seq 1 "$SAMPLES"); do
    import -window root "$TRY" 2>/dev/null || true
    SZ="$(stat -c%s "$TRY" 2>/dev/null || echo 0)"
    # `if`, not `[ ... ] && { ...; }`: as the last command in the body the
    # `&&` form returns non-zero on every non-maximum iteration and kills the
    # loop under `set -e`.
    if [[ "$SZ" -gt "$BEST" ]]; then
        BEST="$SZ"
        cp "$TRY" "$OUT"
    fi
    # Without this the loop keeps shooting blanks after the render has exited.
    kill -0 "$SHOT" 2>/dev/null || break
    sleep 1
done

printf 'best frame: %s bytes -> %s\n' "$BEST" "$OUT"
if [[ "$BEST" -lt 10000 ]]; then
    echo "error: every frame was the backdrop (or nothing); the lock did not paint" >&2
    exit 1
fi
