#!/bin/bash

# ============================================================================
# The app's desktop coach path against the REAL relay, in one call.
#
# Starts leetcode_coach.tests._live_relay (the real relay; claude, Firebase,
# LeetCode, Ollama and Anki faked; every file under a temp dir) on a free
# loopback port, never 8777, then drives it through the wrapper's proxy with
# tool/coach_live_check.dart, and tears everything down on exit.
#
# Usage: coach_live_check.sh flow|slow [FIXTURES_DIR]
#   flow  a session up to step 4 (relay pace 0.5 s, so it fits one call)
#   slow  one 35 s coach turn through a wrapper with a 30 s per-call timeout
# Needs: python3 (system, with this repo's deps), node, dart.
# ============================================================================

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_NAME
APP_DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
readonly APP_DIR
REPO_DIR="$(cd "${APP_DIR}/.." && pwd)"
readonly REPO_DIR
WORK="$(mktemp -d /tmp/lg-coach-live.XXXXXX)"
readonly WORK
RELAY_PID=""

die() {
	echo "${SCRIPT_NAME}: $*" >&2
	exit 1
}

cleanup() {
	if [[ -n ${RELAY_PID} ]]; then
		kill "${RELAY_PID}" 2>/dev/null || true
		wait "${RELAY_PID}" 2>/dev/null || true
	fi
	rm -rf "${WORK}"
}
trap cleanup EXIT

# The fake claude's answers, in call order per kind (coach / haiku).
write_script() {
	local scenario="$1" opener reply
	opener='{"result": "Start with the constraint: what does it rule out? <!-- rung: H0 -->"}'
	reply='{"result": "Which property lets a value undo itself? <!-- rung: H0 -->"}'
	mkdir -p "${WORK}/claude"
	if [[ ${scenario} == slow ]]; then
		reply='{"result": "That took a while. <!-- rung: H0 -->", "sleep": 35}'
	fi
	cat >"${WORK}/claude/script.json" <<-JSON
		{"coach": [${opener}, ${reply}],
		 "haiku": [
		  {"result": "{\"grade\": \"partial\", \"feedback\": \"Say what the space bound rules out.\"}"},
		  {"result": "{\"grade\": \"pass\", \"feedback\": \"\"}"}]}
	JSON
}

wait_for_file() {
	local file="$1" _
	for _ in $(seq 100); do
		[[ -s ${file} ]] && return 0
		sleep 0.1
	done
	die "relay did not start (see ${WORK}/relay.log)"
}

main() {
	local scenario="${1:-}" fixtures="${2:-}" pace port
	case "${scenario}" in
	flow) pace=0.5 ;;
	slow) pace=3 ;;
	*) die "usage: ${SCRIPT_NAME} flow|slow [FIXTURES_DIR]" ;;
	esac
	[[ -z ${fixtures} ]] || mkdir -p "${fixtures}"
	write_script "${scenario}"
	(
		cd "${REPO_DIR}"
		export LEETCODE_CLAUDE_BIN="${REPO_DIR}/leetcode_coach/tests/_fake_claude.py"
		export FAKE_CLAUDE_DIR="${WORK}/claude"
		LEETCODE_NODE_BIN="$(command -v node)" || die "needs node"
		export LEETCODE_NODE_BIN
		# Belt and braces: the harness wires its own fakes, but none of these
		# may ever fall through to the real relay's files or Firebase.
		export LEETCODE_COACH_RTDB_URL="http://127.0.0.1:9"
		export LEETCODE_COACH_RELAY_DIR="${WORK}/relay"
		export LEETCODE_COACH_SESSIONS_DIR="${WORK}/sessions"
		export LEETCODE_COACH_CARDS_DRY_RUN=1
		exec /usr/bin/python3 -m leetcode_coach.tests._live_relay 0 "${WORK}" "${pace}"
	) >"${WORK}/relay.log" 2>&1 &
	RELAY_PID=$!
	wait_for_file "${WORK}/ready"
	port="$(cat "${WORK}/ready")"
	echo "relay on 127.0.0.1:${port} (pace ${pace} s)"
	(cd "${APP_DIR}" && dart run tool/coach_live_check.dart "${port}" "${scenario}" "${fixtures}") ||
		{
			tail -20 "${WORK}/relay.log" >&2
			exit 1
		}
	echo "claude calls: $(wc -l <"${WORK}/claude/calls.jsonl")"
}

main "$@"
