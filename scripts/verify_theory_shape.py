#!/usr/bin/env python3
"""Prove the tutor's files still have the shape ``_theory`` reads.

``test_theory.py`` builds its tutor directory by hand, so it can only repeat
what its author measured on 2026-11-21. If the tutor renames ``"taught"``,
moves ``cards.json`` or keys cards differently, the suite stays green and every
block silently reads as "theory unknown". This reads the real data instead::

    python3 -m scripts.verify_theory_shape

Read-only. Skips loudly at exit 0 when the tutor has no data on this machine --
a missing precondition, not a shape change. Checked:

* ``log.jsonl`` holds ``taught`` events carrying string ``s`` (subject) and
  ``c`` (card); ``untaught`` events, if any, carry the same two strings;
* every ``subjects/<id>/cards.json`` is an object of rows with a string
  ``module`` and a boolean ``suspended``;
* the two join: a taught card of a subject that still exists is a key of that
  subject's ``cards.json`` (cards are suspended, never deleted).

It ends by printing what the guard would show for the shipped curriculum.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import TYPE_CHECKING

from leetcode_guard._curriculum import SHIPPED_CURRICULUM_FILE, load_curriculum
from leetcode_guard._theory import TUTOR_DATA_DIR, unit_theory

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

_EXIT_OK = 0
_EXIT_FAIL = 1


def _events(log: Path) -> list[dict[str, object]]:
    """Every parseable object line of the log."""
    events: list[dict[str, object]] = []
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except ValueError as exc:
            _logger.warning("skipping a torn log line %r: %s", line[:40], exc)
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _check(results: list[bool], label: str, *, passed: bool) -> None:
    """Print one PASS/FAIL line and record it."""
    print(f"{'PASS' if passed else 'FAIL'}: {label}")
    results.append(passed)


def _cards_by_subject(root: Path, results: list[bool]) -> dict[str, set[str]]:
    """Card ids per subject, checking each file's row shape on the way."""
    cards: dict[str, set[str]] = {}
    for path in sorted((root / "subjects").glob("*/cards.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        rows = document.values() if isinstance(document, dict) else [None]
        shaped = all(
            isinstance(row, dict)
            and isinstance(row.get("module"), str)
            and isinstance(row.get("suspended"), bool)
            for row in rows
        )
        _check(
            results,
            f"cards rows have module + suspended ({path.parent.name})",
            passed=shaped,
        )
        if isinstance(document, dict):
            cards[path.parent.name] = set(document)
    return cards


def main() -> int:
    """Check the live tutor files against what ``_theory`` assumes."""
    root = TUTOR_DATA_DIR
    log = root / "log.jsonl"
    if not log.exists() or not (root / "subjects").is_dir():
        print(f"SKIP: no tutor data at {root}; nothing to check the shape against.")
        return _EXIT_OK

    results: list[bool] = []
    taught = [event for event in _events(log) if event.get("k") == "taught"]
    _check(results, f"the log holds taught events ({len(taught)})", passed=bool(taught))
    keyed = all(
        isinstance(e.get("s"), str) and isinstance(e.get("c"), str) for e in taught
    )
    _check(results, "every taught event names a subject and a card", passed=keyed)

    untaught = [event for event in _events(log) if event.get("k") == "untaught"]
    _check(
        results,
        f"every untaught event names a subject and a card ({len(untaught)})",
        passed=all(
            isinstance(e.get("s"), str) and isinstance(e.get("c"), str)
            for e in untaught
        ),
    )

    cards = _cards_by_subject(root, results)
    _check(
        results, f"at least one subject has cards ({len(cards)})", passed=bool(cards)
    )
    joinable = [e for e in taught if e.get("s") in cards]
    orphans = [e for e in joinable if e.get("c") not in cards[str(e.get("s"))]]
    _check(
        results,
        f"taught cards are keys of their subject's cards ({len(joinable)} checked)",
        passed=bool(joinable) and not orphans,
    )

    curriculum = load_curriculum(SHIPPED_CURRICULUM_FILE)
    if curriculum is not None:
        print("\nshipped curriculum, as the guard reads it now:")
        for unit, state in zip(curriculum.units, unit_theory(curriculum), strict=True):
            print(f"  {unit.unit_id:16} {state.value}")
    return _EXIT_OK if all(results) else _EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
