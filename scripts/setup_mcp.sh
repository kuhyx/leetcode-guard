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
# What the last good install was made from. The install is editable, so code
# edits never need it; only pyproject.toml (deps, pins) or a moved repo does.
# Re-running it unconditionally re-cloned the git deps, ~25 s per deploy.
readonly STAMP="${VENV_DIR}/.setup_mcp.sha256"

log() { printf 'setup_mcp: %s\n' "$1" >&2; }

install_key() {
    { printf '%s\n' "${REPO_DIR}"; cat "${REPO_DIR}/pyproject.toml"; } | sha256sum | cut -d' ' -f1
}

verify_import() {
    "${VENV_DIR}/bin/python" -c \
        "import mcp, leetcode_guard._mcp; print('mcp + leetcode_guard._mcp import OK')"
}

main() {
    if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
        log "creating ${VENV_DIR}"
        python3 -m venv "${VENV_DIR}"
    fi

    local key
    key="$(install_key)"
    # The stamp only skips the install when the import still works: a venv
    # broken some other way is reinstalled, never vouched for.
    if [[ -f "${STAMP}" && "$(cat "${STAMP}")" == "${key}" ]] && verify_import; then
        log "pyproject.toml unchanged since the last install -- skipped"
        log "done -- .mcp.json already points at ${VENV_DIR}/bin/python"
        return 0
    fi

    rm -f -- "${STAMP}"
    log "installing leetcode-guard[mcp] into the venv"
    "${VENV_DIR}/bin/python" -m pip install --quiet --upgrade pip
    "${VENV_DIR}/bin/python" -m pip install --quiet -e "${REPO_DIR}[mcp]"

    # The server module, not the package root: importing `leetcode_guard`
    # alone passed for a week while `_mcp` could not import `freedays`, and
    # the only symptom was the client reporting "Connection closed".
    log "verifying the server module imports in this interpreter"
    verify_import
    printf '%s' "${key}" >"${STAMP}"

    log "done -- .mcp.json already points at ${VENV_DIR}/bin/python"
}

main "$@"
