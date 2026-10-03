#!/bin/bash

# ============================================================================
# Load extension/ into Helium on every launch via helium-browser-flags.conf.
#
# Helium's wrapper (/opt/helium-browser-bin/helium-wrapper) appends each line
# of ~/.config/helium-browser-flags.conf to its command line, and Chromium 154
# still honours --load-extension (verify_nudge_extension.py proves it), so this
# needs no click in chrome://extensions. Idempotent; takes effect the next time
# Helium starts -- it never restarts a running browser.
# ============================================================================

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
readonly REPO
readonly EXTENSION="$REPO/extension"
readonly FLAGS_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/helium-browser-flags.conf"

log() { printf 'nudge-extension: %s\n' "$1" >&2; }

main() {
    [[ -f "$EXTENSION/manifest.json" ]] || {
        log "no manifest at $EXTENSION"
        exit 1
    }
    touch "$FLAGS_FILE"
    if grep -qF -- "$EXTENSION" "$FLAGS_FILE"; then
        log "already loaded from $FLAGS_FILE"
        return 0
    fi
    if grep -q -- '^--load-extension=' "$FLAGS_FILE"; then
        # Chromium honours only one --load-extension; extend its list instead.
        local line updated=""
        while IFS= read -r line; do
            [[ $line == --load-extension=* ]] && line="$line,$EXTENSION"
            updated+="$line"$'\n'
        done < "$FLAGS_FILE"
        # Written in place rather than mv'd, so a symlinked config stays linked.
        printf '%s' "$updated" > "$FLAGS_FILE"
    else
        printf -- '--load-extension=%s\n' "$EXTENSION" >> "$FLAGS_FILE"
    fi
    log "added to $FLAGS_FILE -- restart Helium once to load it"
}

main "$@"; exit $?
