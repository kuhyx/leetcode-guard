"""Negative cache for difficulty lookups: ask about a dead problem once a day.

A problem LeetCode answers with ``question: null`` (deleted, unpublished) never
gets a difficulty row, so every harvester tick used to re-ask -- up to
``DEFAULT_MAX_FETCH`` requests a minute, forever. The slug is recorded here with
the time of the answer and skipped until :data:`RETRY_SECONDS` have passed.

The file is deliberately unsigned and decides nothing: it only schedules
requests. Editing it can delay a lookup, never change a weight; the credit is
priced Easy (with the aggregated warning of
:meth:`leetcode_guard._difficulty.WeightTable.warn_unknown`) either way. A
transport failure is NOT recorded: it says nothing about the problem.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard._atomic_json import write_json
from leetcode_guard._read_json import MISSING, read_json

if TYPE_CHECKING:
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)

RETRY_SECONDS: Final = 24 * 3600
"""At most one lookup per unresolved slug per day."""


def load_unresolved(path: Path) -> dict[str, float]:
    """``slug -> epoch seconds`` of its last unresolved answer; junk reads as none."""
    raw = read_json(path, _logger, "ignoring the unresolved-difficulty marks: %s")
    if raw is MISSING:
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        slug: float(stamp)
        for slug, stamp in raw.items()
        if isinstance(stamp, (int, float)) and not isinstance(stamp, bool)
    }


def save_unresolved(path: Path, marks: dict[str, float]) -> bool:
    """Persist the marks atomically; ``False`` (logged) rather than raising."""
    try:
        write_json(path, marks)
    except OSError as exc:
        _logger.warning("could not write the unresolved-difficulty marks: %s", exc)
        return False
    return True


def is_backed_off(marks: dict[str, float], slug: str, *, now: float) -> bool:
    """Whether ``slug`` was answered unresolved less than a day ago.

    A mark from the future (clock set back) does not suppress: a bad clock must
    never turn a one-day back-off into a permanent one.
    """
    stamp = marks.get(slug)
    return stamp is not None and 0 <= now - stamp < RETRY_SECONDS
