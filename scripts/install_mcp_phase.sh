#!/bin/bash
# ============================================================================
# install_mcp_phase.sh -- sourced by install.sh (uses its log, fail,
# REPO_DIR and INSTALL_TMPDIR).
#
# The MCP venv pins its own copies of gatelock/freedays/sickdays; without a
# refresh a dependency bump leaves the server failing to import, which the
# client reports only as "Connection closed" (2026-10-03: freedays 0.1.0).
# Its pip shares nothing with the system-python pip, and one after the other
# they took 31 s + 27 s, which put a deploy over the 60 s action cap
# (68 s, 2026-11-21). So it runs beside the system phase; its output goes to a
# file and is replayed whole, never interleaved with install.sh's own.
#
# Both exit codes count: a failed system phase still waits for the MCP setup
# (the EXIT trap, so the scratch dir is not pulled from under its pip), and a
# failed MCP setup fails the install after everything else has run.
# ============================================================================
# shellcheck shell=bash

MCP_PID=""
MCP_LOG=""

start_mcp_setup() {
    MCP_LOG="${INSTALL_TMPDIR}/setup_mcp.log"
    "${REPO_DIR}/scripts/setup_mcp.sh" > "$MCP_LOG" 2>&1 &
    MCP_PID=$!
}

finish_mcp_setup() {
    local pid="$MCP_PID" status=0
    MCP_PID=""
    wait "$pid" || status=$?
    cat -- "$MCP_LOG" >&2
    ((status == 0)) || fail "scripts/setup_mcp.sh (the MCP venv) exited $status"
}

# EXIT trap of install.sh.
cleanup() {
    local status=0
    if [[ -n "$MCP_PID" ]]; then
        wait "$MCP_PID" || status=$?
        cat -- "$MCP_LOG" >&2
        ((status == 0)) || log "the MCP venv setup failed as well (exit $status)"
    fi
    rm -rf -- "$INSTALL_TMPDIR"
}
