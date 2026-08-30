#!/bin/bash
# ============================================================================
# install.sh -- install leetcode-guard for real use.
#
# Installs into the SYSTEM python's user site-packages, not a venv, because
# that is what the systemd unit actually runs. Testing in a dev venv and
# shipping to /usr/bin/python3 is how diet_guard was silently dead for three
# days, so this script verifies the imports with the exact interpreter the
# service will use.
#
# Idempotent. Safe to re-run after any change.
# ============================================================================

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_DIR
readonly SYSTEM_PYTHON="/usr/bin/python3"
readonly UNIT_DIR="${HOME}/.config/systemd/user"
readonly HMAC_KEY="/etc/workout-locker/hmac.key"
readonly GATELOCK_SRC="${HOME}/utils/gatelock"

log() { printf 'install: %s\n' "$1" >&2; }
fail() { printf 'install: FAILED -- %s\n' "$1" >&2; exit 1; }

install_package() {
    log "installing into the system python's user site-packages"
    "$SYSTEM_PYTHON" -m pip install --user --break-system-packages -e "$REPO_DIR" \
        || fail "pip install"
}

preserve_editable_gatelock() {
    # `pip install -e .` resolves our pinned `gatelock @ git+...` dependency
    # and installs it NON-editably, silently replacing an editable install
    # pointing at ~/utils/gatelock. That breaks live editing across all four
    # lockers, and it is invisible until someone edits gatelock and wonders
    # why nothing changed. Caught twice by hand; now handled here.
    if [[ ! -d "$GATELOCK_SRC" ]]; then
        return
    fi
    local resolved
    resolved="$("$SYSTEM_PYTHON" -c 'import gatelock; print(gatelock.__file__)' 2>/dev/null || true)"
    if [[ "$resolved" == "$GATELOCK_SRC"* ]]; then
        log "gatelock is still editable ($GATELOCK_SRC)"
        return
    fi
    log "restoring the editable gatelock install at $GATELOCK_SRC"
    "$SYSTEM_PYTHON" -m pip install --user --break-system-packages -q -e "$GATELOCK_SRC" \
        || fail "could not restore the editable gatelock"
}

verify_imports() {
    # The check that matters: every runtime dependency must resolve for the
    # interpreter systemd will launch, not for whatever is on $PATH now.
    log "verifying imports with $SYSTEM_PYTHON"
    "$SYSTEM_PYTHON" -c \
        "import leetcode_guard, gatelock, crdt_sync, requests; print('imports OK')" \
        || fail "a runtime dependency is missing from the system python"
}

ensure_hmac_key() {
    # Shared with the sibling lockers on purpose -- one key, one place.
    if [[ -r "$HMAC_KEY" ]]; then
        log "HMAC key present and readable at $HMAC_KEY"
        return
    fi
    if [[ -e "$HMAC_KEY" ]]; then
        fail "$HMAC_KEY exists but is not readable -- ledger integrity would be off"
    fi
    log "no HMAC key at $HMAC_KEY"
    log "  ledger entries will be unsigned until one exists."
    log "  create it with: sudo install -d -m 755 /etc/workout-locker &&"
    log "    sudo $SYSTEM_PYTHON -c \\"
    log "      'from gatelock.log_integrity import generate_hmac_key; generate_hmac_key()'"
}

install_units() {
    log "installing systemd user units into $UNIT_DIR"
    mkdir -p "$UNIT_DIR"
    install -m 644 "$REPO_DIR/leetcode-guard.service" "$UNIT_DIR/"
    install -m 644 "$REPO_DIR/leetcode-guard.timer" "$UNIT_DIR/"
    install -m 644 "$REPO_DIR/leetcode-guard-web.service" "$UNIT_DIR/"
    systemctl --user daemon-reload
    systemctl --user enable --now leetcode-guard.timer
    # The status API is what steam-backlog-enforcer falls back to when it
    # cannot read the ledger directly; it must be up whenever the user is.
    systemctl --user enable --now leetcode-guard-web.service
    log "timer enabled; next run:"
    systemctl --user list-timers leetcode-guard.timer --no-pager || true
    systemctl --user --no-pager --lines=0 status leetcode-guard-web.service || true
}

install_tray() {
    # i3 launches the tray from ~/.config/i3/scripts (screen-locker's lives
    # there too). Copied rather than symlinked, matching how the sibling
    # units are installed.
    local dest="${HOME}/.config/i3/scripts"
    mkdir -p "$dest"
    install -m 755 "$REPO_DIR/scripts/leetcode_guard_tray.py" "$dest/"
    log "tray installed to $dest/leetcode_guard_tray.py"

    local i3_config="${HOME}/.config/i3/config"
    local exec_line="exec --no-startup-id /usr/bin/python3 $dest/leetcode_guard_tray.py"
    if [[ -f "$i3_config" ]] && ! grep -qF "leetcode_guard_tray.py" "$i3_config"; then
        {
            printf '\n# leetcode-guard status tray. Left-click TOGGLES the status window\n'
            printf '# (open/close); right-click gives refresh and quit.\n'
            printf '%s\n' "$exec_line"
        } >> "$i3_config"
        log "added the tray to $i3_config -- reload i3 (\$mod+Shift+r) to start it"
    else
        log "tray already referenced in $i3_config (or no i3 config found)"
    fi
}

main() {
    install_package
    preserve_editable_gatelock
    verify_imports
    ensure_hmac_key
    install_units
    install_tray
    log "done. Try: python3 -m leetcode_guard --check"
}

main "$@"
