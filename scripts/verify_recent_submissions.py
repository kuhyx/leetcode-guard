#!/usr/bin/env python3
"""Prove ``recentSubmissionList`` still has the shape the fixtures claim.

``test_attempt_queries.py`` builds its rows from
``_recent_submissions_fixtures``, which repeats what was measured on 2026-11-21.
A fixture cannot notice LeetCode renaming a key or sending ``timestamp`` as a
number, and the failed-submission record would silently shrink to nothing. So
this asks the live endpoint instead::

    python3 -m scripts.verify_recent_submissions

Run as a *module*, like the other harnesses here, so ``leetcode_guard``
resolves from the checkout. Checked on the real answer: every row has exactly
the fixture's keys, every ``timestamp`` is a digit string, at most 20 rows came
back, every ``statusDisplay`` is a non-empty string, and the typed parser keeps
every row.

The query is public, so no cookie is involved. An unreachable endpoint, a
GraphQL error or a null payload (an expired session or a rate limit looks the
same) is "could not check"; an empty list is a real answer with no row to
compare. Both are *precondition* failures: it skips loudly (a separate line
each) and exits 0 rather than blocking unrelated pushes, and exits 1 only when
the shape itself has moved.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Final

from leetcode_guard._attempt_queries import (
    RECENT_SUBMISSIONS_QUERY,
    fetch_recent_submissions,
    recent_submissions_variables,
)
from leetcode_guard._settings import build_client
from leetcode_guard.tests._recent_submissions_fixtures import MAX_ROWS, ROW_KEYS

if TYPE_CHECKING:
    from collections.abc import Callable

    from leetcode_guard._leetcode import GraphQLResult, PostFn

_EXIT_OK: Final = 0
_EXIT_FAILED: Final = 1
_FIELD: Final = "recentSubmissionList"


def _check(results: list[bool], label: str, *, passed: bool) -> None:
    """Record one assertion and print it either way."""
    results.append(passed)
    print(f"  [{'PASS' if passed else 'FAIL'}] {label}")


def _rows_of(result: GraphQLResult) -> list[object] | None:
    """The rows of a real answer, or ``None`` when there is nothing to compare."""
    rows = (result.data or {}).get(_FIELD)
    if result.transport_error or result.errors or not isinstance(rows, list):
        return None
    return rows


def _all(rows: list[object], test: Callable[[dict[str, object]], bool]) -> bool:
    """Whether every row is an object passing ``test``."""
    return all(isinstance(row, dict) and test(row) for row in rows)


def verify(post: PostFn, username: str) -> int:
    """Ask once and compare the answer with the fixture's shape."""
    result = post(RECENT_SUBMISSIONS_QUERY, recent_submissions_variables(username))
    rows = _rows_of(result)
    if rows is None:
        print("SKIP: could not check (unreachable, GraphQL error, or a null payload")
        print("      from a rate limit). Nothing was verified; run again later.")
        return _EXIT_OK
    if not rows:
        print("SKIP: LeetCode answered with an empty list, a real answer but there")
        print("      is no row to compare. Nothing was verified.")
        return _EXIT_OK

    print(f"got {len(rows)} row(s) from the live endpoint\n")
    results: list[bool] = []
    _check(
        results,
        f"every row has exactly the keys {sorted(ROW_KEYS)}",
        passed=_all(rows, lambda row: set(row) == ROW_KEYS),
    )
    _check(
        results,
        "every timestamp is a digit string",
        passed=_all(
            rows,
            lambda row: (
                isinstance(row.get("timestamp"), str)
                and str(row["timestamp"]).isascii()
                and str(row["timestamp"]).isdigit()
            ),
        ),
    )
    _check(results, f"at most {MAX_ROWS} rows", passed=len(rows) <= MAX_ROWS)
    _check(
        results,
        "every statusDisplay is a non-empty string",
        passed=_all(
            rows,
            lambda row: (
                isinstance(row.get("statusDisplay"), str) and bool(row["statusDisplay"])
            ),
        ),
    )
    kept = fetch_recent_submissions(lambda *_: result, username)
    _check(
        results,
        "the typed parser keeps every row",
        passed=kept is not None and len(kept) == len(rows),
    )

    if all(results):
        print(f"\nOK: {len(results)} checks passed.")
        return _EXIT_OK
    print(f"\nFAILED: {results.count(False)} of {len(results)} checks failed.")
    print("recentSubmissionList has moved. Update _recent_submissions_fixtures,")
    print("_attempt_queries and its tests together, then re-run this.")
    return _EXIT_FAILED


def main() -> int:
    """Check the live endpoint as the configured user."""
    client = build_client()
    return verify(client.post, client.username)


if __name__ == "__main__":
    sys.exit(main())
