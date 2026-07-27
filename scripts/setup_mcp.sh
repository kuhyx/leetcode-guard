#!/bin/bash
# ============================================================================
# setup_mcp.sh -- set up the dedicated virtualenv that hosts the MCP server.
#
# Claude Code spawns `python -m leetcode_guard._mcp` over stdio using the
# interpreter named in .mcp.json. The MCP SDK lives ONLY in this venv: it is an
# optional dependency, deliberately kept out of the system/CLI/systemd python
# path so the gate itself never has to import it.
#
# Both `mcp` and `leetcode_guard` must be importable by this one interpreter,
# or the server fails to start in a way that looks like a hang rather than an
# error -- hence the explicit verification step at the end.
#
# Idempotent: safe to re-run after any dependency change.
# ============================================================================

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly REPO_DIR
readonly VENV_DIR="${HOME}/.venvs/leetcode-guard-mcp"

log() { printf 'setup_mcp: %s\n' "$1" >&2; }

main() {
    if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
        log "creating ${VENV_DIR}"
        python3 -m venv "${VENV_DIR}"
    fi

    log "installing leetcode-guard[mcp] into the venv"
    "${VENV_DIR}/bin/python" -m pip install --quiet --upgrade pip
    "${VENV_DIR}/bin/python" -m pip install --quiet -e "${REPO_DIR}[mcp]"

    log "verifying both imports resolve in the same interpreter"
    "${VENV_DIR}/bin/python" -c \
        "import mcp, leetcode_guard; print('mcp + leetcode_guard import OK')"

    log "done -- .mcp.json already points at ${VENV_DIR}/bin/python"
}

main "$@"
