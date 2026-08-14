#!/usr/bin/env python3
"""Prove that LeetCode's ``status`` still means what the fixtures claim.

**No unit test can answer this.** Every solved-state test in the suite asserts
against ``_net_fixtures.status_result``, and a fixture can only repeat what its
author believed the endpoint does. On 2026-08-14 that belief was wrong -- the
docstring said a ``null`` status meant "signed out or expired", inferred from a
dead cookie where everything is null -- so the tests passed while the code
shipped the same error. A mock cannot falsify the assumption it was built from.

So this asks the live endpoint instead, and checks the three values are
genuinely distinct::

    python3 -m scripts.verify_solved_semantics

Run as a *module*, like the other harnesses here: ``-m`` puts the repo root on
``sys.path``, so ``leetcode_guard`` resolves from the checkout rather than from
wherever it happens to be installed.

What is being defended:

* ``"ac"`` for a problem the ledger records as solved. If this regresses, the
  live check silently stops hiding anything.
* ``None`` for a problem never attempted -- **not** ``"notac"``. This is the one
  that broke. ``"notac"`` is reserved for a failed submission on record.
* ``signed_in`` still true across an all-null sweep. This is the assertion that
  matters most: a signed-in user browsing problems they have never opened
  produces exactly that, and reading it as an expired session made the lock
  announce it could not check while holding a verified cookie **and** abandon
  the rest of the sweep -- so a solved problem further down survived the check
  meant to remove it.

A dead cookie is a *precondition* failure, not a semantic violation. It expires
about every two weeks, so this skips loudly and exits 0 in that case rather
than blocking unrelated work; run ``python3 -m leetcode_guard --login`` and try
again. It fails hard only when the semantics themselves have moved.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Final

from leetcode_guard._constants import LEDGER_FILE
from leetcode_guard._ledger_io import load_ledger, solved_slugs
from leetcode_guard._live_solved import check_solved, parse_status
from leetcode_guard._queries import STATUS_QUERY, status_variables
from leetcode_guard._settings import build_client

if TYPE_CHECKING:
    from leetcode_guard._leetcode import PostFn

_EXIT_OK: Final = 0
_EXIT_FAILED: Final = 1

_NEVER_ATTEMPTED: Final = (
    "build-array-from-permutation",
    "convert-the-temperature",
)
"""Free, long-standing problems kuhy has not solved.

If one of these is ever actually solved the harness reports a mismatch rather
than a false pass -- the failure text says to swap the slug, which is cheaper
than silently weakening the check.
"""


def _check(
    results: list[bool], label: str, *, actual: object, expected: object
) -> None:
    """Record one assertion and print it either way."""
    ok = actual == expected
    results.append(ok)
    verdict = "PASS" if ok else "FAIL"
    print(f"  [{verdict}] {label} (expected {expected!r}, got {actual!r})")


def _status_of(post: PostFn, slug: str) -> str | None:
    """One problem's raw status, straight from the endpoint."""
    return parse_status(post(STATUS_QUERY, status_variables(slug)).data)


def main() -> int:
    """Check the three status values against the live endpoint."""
    client = build_client()
    known_solved = sorted(solved_slugs(load_ledger(LEDGER_FILE)))
    if not known_solved:
        print("SKIP: the ledger records no solves yet, so there is nothing to")
        print("      check 'ac' against. Solve one problem and re-run.")
        return _EXIT_OK

    probe_slug = known_solved[0]
    solved_status = _status_of(client.post, probe_slug)
    if solved_status is None:
        print(f"SKIP: LeetCode returned null for {probe_slug}, which the ledger")
        print("      records as solved -- the session is expired or unreachable.")
        print("      Run: python3 -m leetcode_guard --login")
        return _EXIT_OK

    print(f"session is live (status for {probe_slug} came back non-null)\n")
    results: list[bool] = []

    _check(
        results,
        f"a solved problem reports 'ac' ({probe_slug})",
        actual=solved_status,
        expected="ac",
    )

    for slug in _NEVER_ATTEMPTED:
        _check(
            results,
            f"a never-attempted problem reports null, not 'notac' ({slug})",
            actual=_status_of(client.post, slug),
            expected=None,
        )

    # The regression that shipped: an all-null sweep is what a signed-in user
    # gets for problems they have never opened, and must not read as a dead
    # session.
    sweep = check_solved(client.post, list(_NEVER_ATTEMPTED))
    _check(
        results,
        "an all-null sweep still counts as signed in",
        actual=sweep.signed_in,
        expected=True,
    )
    _check(
        results,
        "an all-null sweep answers for every problem asked",
        actual=sweep.checked,
        expected=len(_NEVER_ATTEMPTED),
    )
    _check(
        results,
        "an all-null sweep recognises no statuses",
        actual=sweep.recognised,
        expected=0,
    )
    _check(
        results,
        "an all-null sweep reports nothing solved",
        actual=sorted(sweep.solved),
        expected=[],
    )

    # And the positive direction: a known solve is still detected end to end.
    solved_sweep = check_solved(client.post, [probe_slug])
    _check(
        results,
        "a known solve is detected by the sweep",
        actual=sorted(solved_sweep.solved),
        expected=[probe_slug],
    )

    if all(results):
        print(f"\nOK: {len(results)} checks passed.")
        return _EXIT_OK
    print(f"\nFAILED: {results.count(False)} of {len(results)} checks failed.")
    print("LeetCode's status semantics have moved, or a slug in")
    print("_NEVER_ATTEMPTED has since been solved. Check which before")
    print("changing any code that reads `status`.")
    return _EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
