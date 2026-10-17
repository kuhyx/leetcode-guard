#!/bin/bash
# ============================================================================
# ci_mirror.sh — run the exact CI gates locally before a push can leave.
#
# Why: the installed pre-commit hook only checks *staged* files, and the local
# dev environment already has every dependency installed. CI does neither — it
# runs `pre-commit run --all-files` and installs a fresh environment from
# requirements.txt. That gap is why green-locally repos went red in CI
# (missing runtime deps, --all-files lint debt, order-dependent test flakes).
#
# Usage: scripts/ci_mirror.sh <stage> [pytest args...]
#   venv       a venv built ONLY from requirements.txt (mirrors the Tests
#              workflow's install), rebuilt only when requirements.txt changes
#              (hash-gated so day-to-day runs stay fast);
#   precommit  `pre-commit run --all-files` (mirrors the pre-commit workflow);
#   pytest     `python -m pytest -n auto --dist worksteal` in that clean venv
#              (mirrors Tests; extra args are passed through);
#   render     the real-Tk renders under Xvfb (mirrors the real-tk-render job).
#              The suite mocks tkinter away, so without this a widget
#              regression is green locally and red in CI;
#   all        every stage above, in that order (the default).
#
# Each stage is its own manual-stage pre-commit hook (ci-venv, ci-precommit,
# ci-pytest, ci-render) so no single call outlives the 60 s action cap;
# `scripts/check_gate_stamp.sh full` runs them all. pytest and render call
# ensure_venv themselves, so either is safe to run alone.
# ============================================================================

set -euo pipefail

# Requirements file may be overridden (e.g. testsAndMisc uses meta/…).
REQUIREMENTS_FILE="${REQUIREMENTS_FILE:-requirements.txt}"
readonly REQUIREMENTS_FILE

ROOT="$(git rev-parse --show-toplevel)"
readonly ROOT
cd "$ROOT"

readonly VENV_DIR="$ROOT/.ci-mirror-venv"
readonly HASH_FILE="$VENV_DIR/.requirements.sha256"
readonly REQ_PATH="$ROOT/$REQUIREMENTS_FILE"
readonly RENDER_STATES=(locked unlocked escape outage production)

log() { printf 'ci-mirror: %s\n' "$1" >&2; }

fail() {
    log "FAILED — $1"
    log "CI would be red. Fix the above before pushing."
    exit 1
}

require_file() {
    if [[ ! -f "$REQ_PATH" ]]; then
        fail "requirements file not found: $REQ_PATH"
    fi
}

# Rebuild the venv only when requirements.txt changed since the last build.
ensure_venv() {
    require_file
    local current stored
    current="$(sha256sum "$REQ_PATH" | cut -d' ' -f1)"
    stored=""
    if [[ -f "$HASH_FILE" ]]; then
        stored="$(cat "$HASH_FILE")"
    fi

    if [[ -x "$VENV_DIR/bin/python" && "$current" == "$stored" ]]; then
        log "venv up to date (requirements.txt unchanged)"
        return
    fi

    log "requirements.txt changed — rebuilding clean venv (mirrors CI install)"
    rm -rf "$VENV_DIR"
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip \
        || fail "pip self-upgrade in the clean venv"
    "$VENV_DIR/bin/python" -m pip install --quiet -r "$REQ_PATH" \
        || fail "pip install -r $REQUIREMENTS_FILE (a dep may be undeclared)"
    # Written last: an interrupted build leaves no hash, so the next run
    # rebuilds instead of trusting a half-installed venv.
    printf '%s' "$current" > "$HASH_FILE"
    log "clean venv ready"
}

run_precommit_all_files() {
    log "pre-commit run --all-files (mirrors the pre-commit workflow)"
    pre-commit run --all-files || fail "pre-commit --all-files"
}

# Same flags as the Tests workflow. The 100% branch-coverage bar lives in
# pyproject addopts, and pytest-cov merges the xdist workers' data.
run_pytest_clean_venv() {
    ensure_venv
    log "pytest in the clean venv (mirrors the Tests workflow)"
    "$VENV_DIR/bin/python" -m pytest -n auto -q --dist worksteal "$@" \
        || fail "pytest (clean requirements.txt venv)"
}

# Every state renders concurrently, each on its own Xvfb. `-n <base> -a`
# gives each one a different starting display number: xvfb-run -a only checks
# lock files, so five started at once from the same base would race for :99.
run_real_tk_render() {
    if [[ ! -f scripts/screenshot_states.py ]]; then
        return
    fi
    if ! command -v xvfb-run >/dev/null 2>&1; then
        log "xvfb-run not installed -- SKIPPING the real-Tk render that CI runs"
        return
    fi
    ensure_venv
    log "real-Tk render under Xvfb (mirrors the real-tk-render job)"
    "$VENV_DIR/bin/python" -m pip install --quiet -e . --no-deps \
        || fail "editable install for the render check"

    local logdir
    logdir="$(mktemp -d)"
    # shellcheck disable=SC2064  # expand now: logdir is local to this function
    trap "rm -rf '$logdir'" EXIT

    local -a pids=()
    local i state
    for i in "${!RENDER_STATES[@]}"; do
        state="${RENDER_STATES[$i]}"
        xvfb-run -n "$((200 + 10 * i))" -a -s "-screen 0 1600x1200x24" \
            "$VENV_DIR/bin/python" scripts/screenshot_states.py "$state" \
            >"$logdir/$state.log" 2>&1 &
        pids+=("$!")
    done

    # Wait for every render before judging any, so one failure cannot hide
    # another and no Xvfb is left running behind an early exit.
    local -a failed=()
    for i in "${!RENDER_STATES[@]}"; do
        state="${RENDER_STATES[$i]}"
        if ! wait "${pids[$i]}"; then
            failed+=("$state")
            log "--- render output: $state ---"
            cat "$logdir/$state.log" >&2
        fi
    done
    if ((${#failed[@]})); then
        fail "real-Tk render failed for state(s): ${failed[*]}"
    fi
    log "real-Tk render passed for: ${RENDER_STATES[*]}"
}

main() {
    local stage="${1:-all}"
    if (($#)); then
        shift
    fi
    case "$stage" in
        venv) ensure_venv ;;
        precommit) run_precommit_all_files ;;
        pytest) run_pytest_clean_venv "$@" ;;
        render) run_real_tk_render ;;
        all)
            ensure_venv
            run_precommit_all_files
            run_pytest_clean_venv "$@"
            run_real_tk_render
            log "all CI gates passed locally — safe to push"
            ;;
        *) fail "unknown stage '$stage' (venv|precommit|pytest|render|all)" ;;
    esac
}

main "$@"
