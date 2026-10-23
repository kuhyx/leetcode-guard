#!/bin/bash

# ============================================================================
# leetcode-guard desktop app launcher (the .desktop entry's Exec).
#
# 1. builds the web bundle (build/web) and the wrapper (build/cli) if missing,
# 2. starts the wrapper on 127.0.0.1:8776 unless something already answers,
# 3. opens the app window through the wrapper's --window-only mode, so the
#    browser flags (loopback-only resolver, fixed profile, WM class) live in
#    exactly one place: lib/desktop/browser.dart.
#
# Usage: leetcode_guard_app.sh [--rebuild] [-- WRAPPER_ARGS...]
#   --rebuild      rebuild both bundles even if present
#   WRAPPER_ARGS   passed to the wrapper when this run starts it
#                  (dev: -- --fixture test/fixtures/snapshot_real.json)
# Needs: flutter + dart (only to build), curl, setsid.
# ============================================================================

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_NAME
APP_DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
readonly APP_DIR
readonly PORT=8776
readonly WEB_INDEX="${APP_DIR}/build/web/index.html"
readonly WRAPPER="${APP_DIR}/build/cli/bundle/bin/leetcode_guard_desktop"
readonly LOG_DIR="${XDG_STATE_HOME:-${HOME}/.local/state}/leetcode-guard-app"
readonly WAIT_TRIES=50 # x 0.1 s for the wrapper to start answering

REBUILD=0
WRAPPER_ARGS=()

usage() {
	echo "Usage: ${SCRIPT_NAME} [--rebuild] [-- WRAPPER_ARGS...]"
}

die() {
	echo "${SCRIPT_NAME}: $*" >&2
	exit 1
}

require() {
	local cmd
	for cmd in "$@"; do
		command -v "$cmd" >/dev/null 2>&1 || die "needs '${cmd}' on PATH"
	done
}

wrapper_up() {
	curl -fsS -o /dev/null --max-time 1 "http://127.0.0.1:${PORT}/" 2>/dev/null
}

build_web() {
	require flutter
	echo "Building the web bundle (once)..."
	# --no-web-resources-cdn: CanvasKit from disk, so an offline launch still
	# renders (and the window can reach nothing but loopback anyway).
	(cd "$APP_DIR" && flutter build web --release --no-web-resources-cdn)
}

build_wrapper() {
	require dart
	echo "Building the wrapper (once)..."
	# `dart build cli`, not `dart compile exe`: a dependency has build hooks.
	(cd "$APP_DIR" && dart build cli -o build/cli)
}

start_wrapper() {
	mkdir -p "$LOG_DIR"
	# cwd = APP_DIR: the wrapper finds build/web relative to it. setsid -f
	# detaches it, so closing the window or this script leaves it serving.
	(cd "$APP_DIR" && setsid -f "$WRAPPER" --serve-only "${WRAPPER_ARGS[@]}" \
		>>"${LOG_DIR}/wrapper.log" 2>&1 </dev/null)
	local _
	for _ in $(seq "$WAIT_TRIES"); do
		wrapper_up && return 0
		sleep 0.1
	done
	die "wrapper did not answer on :${PORT}; see ${LOG_DIR}/wrapper.log"
}

main() {
	require curl setsid
	if [[ $REBUILD -eq 1 || ! -f $WEB_INDEX ]]; then build_web; fi
	if [[ $REBUILD -eq 1 || ! -x $WRAPPER ]]; then build_wrapper; fi
	wrapper_up || start_wrapper
	cd "$APP_DIR"
	exec "$WRAPPER" --window-only
}

while [[ $# -gt 0 ]]; do
	case $1 in
	--rebuild)
		REBUILD=1
		shift
		;;
	-h | --help)
		usage
		exit 0
		;;
	--)
		shift
		WRAPPER_ARGS=("$@")
		break
		;;
	*)
		usage >&2
		exit 2
		;;
	esac
done

main
