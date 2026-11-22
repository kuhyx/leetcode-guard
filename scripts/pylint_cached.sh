#!/bin/bash
# The pylint hook's whole-tree gate, skipped when this exact tree already passed.
# It takes ~45 s, over the 60 s action cap once the other hooks run, and a commit
# whose tree is byte-identical to a green one has nothing new to lint. The stamp
# is keyed on every tracked .py file, pyproject.toml, the hook config and the
# pylint version, and is written only after pylint exits 0, so a failure never
# stamps and a fresh CI checkout (no stamp) always lints.
set -euo pipefail

readonly STAMP_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/leetcode-guard-pylint"

tree_hash() {
    {
        git ls-files -z -- '*.py' pyproject.toml .pre-commit-config.yaml |
            xargs -0 sha256sum
        pylint --version
    } | sha256sum | cut -d' ' -f1
}

hash="$(tree_hash)"
if [[ -e "$STAMP_DIR/$hash" ]]; then
    echo "pylint: this tree already passed at 10.00, skipped"
    exit 0
fi
pylint "$@"
mkdir -p "$STAMP_DIR"
touch "$STAMP_DIR/$hash"
