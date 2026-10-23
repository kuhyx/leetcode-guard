#!/bin/bash

# ============================================================================
# Point the /leetcode skill and the `leetcode` command at leetcode_coach/.
#
#   ~/.claude/skills/leetcode -> <repo>/leetcode_coach
#   ~/.local/bin/leetcode     -> <repo>/leetcode_coach/leetcode
#
# Called by install.sh; idempotent. An existing symlink is repointed. A real
# directory at the skill path is replaced only when it is the pre-2026-10-23
# skill this package was moved out of (SKILL.md `name: leetcode` plus
# leetcode_repl.py): it is moved to ~/.claude/backups/, never inside
# ~/.claude/skills, where a backup would load as a second `leetcode` skill.
# Anything else in the way (an unknown directory, a regular file) is refused.
# ============================================================================

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly REPO_DIR
readonly COACH_DIR="${REPO_DIR}/leetcode_coach"
readonly SKILL_LINK="${HOME}/.claude/skills/leetcode"
readonly BIN_LINK="${HOME}/.local/bin/leetcode"
readonly BACKUP_ROOT="${HOME}/.claude/backups"

log() { printf 'link_leetcode_coach: %s\n' "$1" >&2; }
fail() { printf 'link_leetcode_coach: FAILED -- %s\n' "$1" >&2; exit 1; }

is_old_skill_dir() {
    # The directory the package came from: its SKILL.md names the skill and
    # it holds the REPL that now lives in leetcode_coach/.
    local dir="$1"
    [[ -f "${dir}/leetcode_repl.py" ]] \
        && grep -qx 'name: leetcode' "${dir}/SKILL.md" 2>/dev/null
}

clear_path() {
    # Make `path` free for a symlink, or fail without touching anything.
    local path="$1" old_dir_ok="$2"
    if [[ -L "$path" || ! -e "$path" ]]; then
        return
    fi
    if [[ "$old_dir_ok" == "yes" && -d "$path" ]] && is_old_skill_dir "$path"; then
        local backup
        backup="${BACKUP_ROOT}/skill-leetcode-$(date +%Y%m%d-%H%M%S)"
        mkdir -p "$BACKUP_ROOT"
        mv "$path" "$backup"
        log "moved the old skill directory to $backup"
        return
    fi
    fail "$path exists and is not a symlink or the old leetcode skill; not replacing it"
}

link() {
    local target="$1" path="$2" old_dir_ok="$3"
    clear_path "$path" "$old_dir_ok"
    mkdir -p "$(dirname "$path")"
    # -n: replace a symlink to a directory instead of creating a link inside it.
    ln -sfn "$target" "$path"
    log "$path -> $target"
}

main() {
    [[ -f "${COACH_DIR}/SKILL.md" && -x "${COACH_DIR}/leetcode" ]] \
        || fail "no leetcode_coach package at $COACH_DIR"
    link "$COACH_DIR" "$SKILL_LINK" yes
    link "${COACH_DIR}/leetcode" "$BIN_LINK" no
}

main "$@"
