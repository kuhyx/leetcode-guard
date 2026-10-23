#!/bin/bash

# ============================================================================
# Screenshots of the coach session screen, headless, never on kuhy's display.
#
# Runs Xvfb on the first free display >= 90 (no /tmp/.X<n>-lock and no
# socket), the real wrapper over a scripted coach relay on free loopback
# ports (tool/coach_screenshot_server.dart), and Chromium in --app mode with a
# throwaway profile. `run` does one whole session in a single call (under a
# minute) and tears everything down on exit, so nothing outlives it.
#
# Usage:
#   screenshot_coach.sh run W H SCALE OUT.png [X Y]...   # click each X Y
#   (also: start W H SCALE | click X Y | shot OUT.png | stop)
#   Coordinates are physical pixels; e.g. run 3840 2160 2 /tmp/a.png 200 300
# Needs: Xvfb, xdotool, ImageMagick (import), chromium, dart; build/web built.
# ============================================================================

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_NAME
APP_DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
readonly APP_DIR
readonly STATE_DIR="/tmp/lg-coach-shot"
readonly BROWSER="${LEETCODE_GUARD_BROWSER:-/usr/lib/chromium/chromium}"
readonly MIN_SHOT_BYTES=10240

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

free_display() {
	local n
	for n in $(seq 90 140); do
		if [[ ! -e /tmp/.X${n}-lock && ! -e /tmp/.X11-unix/X${n} ]]; then
			echo "$n"
			return 0
		fi
	done
	die "no free X display in 90..140"
}

display() { cat "${STATE_DIR}/display"; }

# --window-size is in device-independent pixels: physical / scale.
dips() { awk -v px="$1" -v s="$2" 'BEGIN { printf "%d", px / s }'; }

wait_for_file() {
	local file="$1" _
	for _ in $(seq 100); do
		[[ -s $file ]] && return 0
		sleep 0.2
	done
	die "timed out waiting for ${file}"
}

cmd_start() {
	local width="$1" height="$2" scale="$3" n
	require Xvfb xdotool import dart
	[[ -x $BROWSER ]] || die "no browser at ${BROWSER}"
	[[ -f "${APP_DIR}/build/web/index.html" ]] || die "build/web missing"
	[[ ! -d $STATE_DIR ]] || die "already started: run '${SCRIPT_NAME} stop'"
	mkdir -p "${STATE_DIR}/profile"
	n="$(free_display)"
	echo ":${n}" >"${STATE_DIR}/display"
	Xvfb ":${n}" -screen 0 "${width}x${height}x24" -nolisten tcp \
		>"${STATE_DIR}/xvfb.log" 2>&1 &
	echo $! >"${STATE_DIR}/xvfb.pid"
	(cd "$APP_DIR" && dart run tool/coach_screenshot_server.dart \
		"${STATE_DIR}/port" >"${STATE_DIR}/server.log" 2>&1) &
	echo $! >"${STATE_DIR}/server.pid"
	wait_for_file "${STATE_DIR}/port"
	DISPLAY=":${n}" "$BROWSER" \
		"--app=http://localhost:$(cat "${STATE_DIR}/port")" \
		"--user-data-dir=${STATE_DIR}/profile" \
		"--force-device-scale-factor=${scale}" \
		"--window-position=0,0" "--window-size=$(dips "$width" "$scale"),$(dips "$height" "$scale")" \
		--no-first-run --no-default-browser-check --disable-extensions \
		--password-store=basic --test-type --no-sandbox \
		>"${STATE_DIR}/browser.log" 2>&1 &
	echo $! >"${STATE_DIR}/browser.pid"
	echo "started on :${n}, wrapper port $(cat "${STATE_DIR}/port")"
}

cmd_click() {
	DISPLAY="$(display)" xdotool mousemove "$1" "$2" click 1
}

cmd_shot() {
	local out="$1" best=0 i size
	for i in 1 2 3 4 5; do
		DISPLAY="$(display)" import -window root "${STATE_DIR}/s${i}.png"
		size="$(stat -c %s "${STATE_DIR}/s${i}.png")"
		if ((size > best)); then
			best="$size"
			cp "${STATE_DIR}/s${i}.png" "$out"
		fi
		sleep 0.5
	done
	((best >= MIN_SHOT_BYTES)) || die "blank capture (${best} bytes)"
	echo "${out}: ${best} bytes"
}

cmd_stop() {
	local name pid
	for name in browser server xvfb; do
		if [[ -f "${STATE_DIR}/${name}.pid" ]]; then
			pid="$(cat "${STATE_DIR}/${name}.pid")"
			# The server pid is a subshell: its dart child goes with the group.
			pkill -P "$pid" 2>/dev/null || true
			kill "$pid" 2>/dev/null || true
		fi
	done
	rm -rf "$STATE_DIR"
}

# Waits for the first paint, clicks each X Y (1.5 s apart), then shoots.
cmd_run() {
	local width="$1" height="$2" scale="$3" out="$4"
	shift 4
	trap cmd_stop EXIT
	cmd_start "$width" "$height" "$scale"
	sleep "${SHOT_SETTLE:-12}"
	while (($# >= 2)); do
		cmd_click "$1" "$2"
		shift 2
		sleep 1.5
	done
	# Park the pointer in the corner so no hover highlight is captured.
	DISPLAY="$(display)" xdotool mousemove "$((width - 1))" "$((height - 1))"
	sleep 2
	cmd_shot "$out"
}

case "${1:-}" in
run) shift && cmd_run "$@" ;;
start) cmd_start "${2:?width}" "${3:?height}" "${4:?scale}" ;;
click) cmd_click "${2:?x}" "${3:?y}" ;;
shot) cmd_shot "${2:?out.png}" ;;
stop) cmd_stop ;;
*) die "usage: ${SCRIPT_NAME} run W H SCALE OUT [X Y]... | start | click | shot | stop" ;;
esac
