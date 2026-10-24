#!/bin/bash
# ============================================================================
# run.sh -- install leetcode-guard's dependencies, then show the gate status.
#
# Usage: ./run.sh [--no-install] [--status options...]
#   --no-install   skip the dependency step and only print the status
#   anything else  is passed to `python3 -m leetcode_guard --status`
#                  (e.g. --by 31.12.2026, --goal Easy=900)
# Exit: --status's own code -- 0 unlocked, 1 locked, 2 cannot verify.
#
# The dependency step is install.sh's own functions (sourced, not copied):
# the editable pip install into the system python's user site, the
# editable-gatelock restore, and the import check with /usr/bin/python3.
# systemd units, the coach relay and the tray are install.sh's job alone.
# ============================================================================

set -euo pipefail

RUN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly RUN_DIR

# shellcheck source=install.sh
source "${RUN_DIR}/install.sh"

install_dependencies() {
    install_package
    preserve_editable_gatelock
    verify_imports
}

main_run() {
    local install=1
    local -a status_args=()
    local arg
    for arg in "$@"; do
        if [[ "$arg" == "--no-install" ]]; then
            install=0
        else
            status_args+=("$arg")
        fi
    done
    if ((install)); then
        install_dependencies
    fi
    "$SYSTEM_PYTHON" -m leetcode_guard --status "${status_args[@]}"
}

main_run "$@"
