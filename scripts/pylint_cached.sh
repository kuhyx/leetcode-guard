#!/bin/bash
# The pylint hook's whole-tree gate, skipped when this exact tree already passed.
#
# Measured 2026-11-22 on this tree (57k lines, score 10.00): one `--jobs=1` run
# took 37-58 s depending on machine load. Of ~44 s, ~5 s was parsing, ~17 s the
# duplicate-code comparison and ~22 s every other checker. Two changes, both
# keeping every checker and every option:
#   1. scripts/pylint_dup_memo.py hashes each file once for duplicate-code
#      instead of once per partner file (same chunks, same R0801 messages):
#      ~17 s -> ~3 s.
#   2. `--jobs=4` for the rest. It gave the same messages as `--jobs=1` on the
#      clean tree and on a tree seeded with an R0801, an R0401 import cycle, an
#      import that resolves only through the init-hook, an unused import and
#      too-many-branches (message-for-message, same counts per check).
# Cold run ~13-17 s at a load average of 16-30, down from ~44-55 s at 22-25.
# The hook pins python3.14, where the `dill` pickling that `--jobs>1` needs
# works; on 3.15 it crashes loudly, so the gate fails closed.
#
# A commit whose tree is byte-identical to a green one has nothing new to lint.
# The stamp is keyed on every tracked .py file (the wrapper included),
# pyproject.toml, the hook config, this script and the pylint version, and is
# written only after pylint exits 0, so a failure never stamps and a fresh CI
# checkout (no stamp) always lints.
set -euo pipefail

readonly STAMP_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/leetcode-guard-pylint"
readonly JOBS=4
readonly WRAPPER="${BASH_SOURCE[0]%/*}/pylint_dup_memo.py"

tree_hash() {
    {
        git ls-files -z -- '*.py' pyproject.toml .pre-commit-config.yaml \
            scripts/pylint_cached.sh | xargs -0 sha256sum
        pylint --version
    } | sha256sum | cut -d' ' -f1
}

hash="$(tree_hash)"
if [[ -e "$STAMP_DIR/$hash" ]]; then
    echo "pylint: this tree already passed at 10.00, skipped"
    exit 0
fi
python3 -P "$WRAPPER" "$@" "--jobs=$JOBS"
mkdir -p "$STAMP_DIR"
touch "$STAMP_DIR/$hash"
