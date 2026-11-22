#!/usr/bin/env python3
"""Run pylint with its duplicate-code line hashing computed once per file.

pylint's ``duplicate-code`` check compares every file with every other file and
recomputes ``hash_lineset`` for both files of every pair, so each file is hashed
once per partner (about 200 times here). The hash is a pure function of the file
and the minimum-similarity setting, and nothing downstream mutates it, so
computing it once per file returns exactly the same chunks and the same R0801
messages. Measured 2026-11-22: ~17 s of a ~44 s whole-tree run, now ~3 s.

Nothing else changes: same checkers, same options, same exit code. If a pylint
upgrade renames or re-signs ``hash_lineset`` this fails with an error instead of
skipping a check, and ``test_pylint_dup_memo.py`` pins message-for-message
equality against an unpatched run.

Run as ``python3 -P scripts/pylint_dup_memo.py <pylint args>``. ``-P`` keeps
``scripts/`` off ``sys.path``, so a script that imports a sibling by bare name is
still reported as an import error, exactly as under the ``pylint`` command.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from pylint import run_pylint
from pylint.checkers import symilar

if TYPE_CHECKING:
    from collections.abc import Callable

_Hashed = tuple[symilar.HashToIndex_T, symilar.IndexToLines_T]


def memoise(
    original: Callable[[symilar.LineSet, int], _Hashed],
) -> Callable[[symilar.LineSet, int], _Hashed]:
    """Wrap ``hash_lineset`` so each line set is hashed once per window size."""
    memo: dict[tuple[int, int], tuple[symilar.LineSet, _Hashed]] = {}

    def hash_lineset(
        lineset: symilar.LineSet,
        min_common_lines: int = symilar.DEFAULT_MIN_SIMILARITY_LINE,
    ) -> _Hashed:
        key = (id(lineset), min_common_lines)
        if key not in memo:
            # The line set is kept in the value so its id cannot be reused.
            memo[key] = (lineset, original(lineset, min_common_lines))
        return memo[key][1]

    return hash_lineset


def main() -> None:
    """Patch the line hashing, then run pylint on this process's arguments."""
    symilar.hash_lineset = memoise(symilar.hash_lineset)
    run_pylint(sys.argv[1:])


if __name__ == "__main__":
    main()
