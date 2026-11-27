"""The parser of the tutor's signed ``review_due.json`` rows (contract C4).

Shared by the display-only reader (``_review_due``: which lock rows to show)
and the review-clear credit (``_review_clear``: a decider). It only types rows
and picks each module's winning one; it decides nothing, reads no file and
imports nothing display-only, so a decider may depend on it.

* verified rows of another kind, or with a malformed ``detail`` (a non-finite
  ``at`` too: it could never be superseded), are skipped;
* per (subject, module) the row with the greatest ``at`` wins, the later one
  in the file on a tie, so an old signed row put back later loses.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

from leetcode_guard._tutor_signed import ModuleKey, Row, detail_of

if TYPE_CHECKING:
    from collections.abc import Sequence

REVIEW_DUE: Final = "review_due.json"
"""The file's name in the tutor's data dir (``_tutor_signed.TUTOR_DIR``)."""
KIND: Final = "review_due"
_MAX_INT_BITS: Final = 1000


def _is_int(value: object) -> bool:
    """An int that is not a bool (JSON ``true`` is not a time)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _finite(at: object) -> float | None:
    """``at`` as a finite float, else ``None`` (NaN, infinity, too big, a bool)."""
    if isinstance(at, bool) or not isinstance(at, (int, float)):
        return None
    if isinstance(at, int) and at.bit_length() > _MAX_INT_BITS:
        return None  # ``float()`` would overflow
    return float(at) if math.isfinite(at) else None


def _typed(row: Row) -> tuple[ModuleKey, float, list[int]] | None:
    """A ``review_due`` row's key, ``at`` and due times, or ``None`` to skip it."""
    detail = detail_of(row)
    subject, module = detail.get("subject"), detail.get("module")
    due, at = detail.get("due_ms"), _finite(detail.get("at"))
    if row.get("kind") != KIND or at is None or not isinstance(due, list):
        return None
    if not isinstance(subject, str) or not isinstance(module, str):
        return None
    if not all(_is_int(t) for t in due):
        return None
    return (subject, module), at, due


def latest_rows(rows: Sequence[Row]) -> dict[ModuleKey, tuple[float, list[int]]]:
    """Each module's winning (``at`` in Unix seconds, due times in Unix ms)."""
    best: dict[ModuleKey, tuple[float, list[int]]] = {}
    for row in rows:
        typed = _typed(row)
        if typed is None:
            continue
        key, at, due = typed
        if key not in best or at >= best[key][0]:
            best[key] = (at, due)
    return best


def latest_due(rows: Sequence[Row]) -> dict[ModuleKey, list[int]]:
    """The due times of each module's winning row (greatest ``at``, then later)."""
    return {key: due for key, (_, due) in latest_rows(rows).items()}
