"""A cleared review pays 1 credit (kuhy 2026-11-27, ``DOCS-review-clear.md``).

``review-clear:<day>:<unit>`` is an ordinary signed ledger row: ``kind:
credit``, ``amount: 1``, ``detail.source: "tutor-theory"`` (so it prices at 1
and counts in ``theory_credits``), ``detail.unit`` and ``detail.cards`` (the
unit's queue size when it was minted). It is minted once per unit per day,
when ALL hold for the current unit ``u`` (THEORY or SOLVE; ``none`` has none):

* the tutor's signed ``ledger.json`` has review-minute rows
  (``activity == "review"``) on u's modules that ended on the day;
* the tutor's signed ``review_due.json`` (read strict: one bad row is "cannot
  check") has a winning row for EVERY module of u, written on the day, with no
  card due at the poll's moment.

Due times are absolute, so an older signed file put back lists the same or
earlier due times and reads MORE cards due, never fewer; "written on the day"
keeps yesterday's clear from paying today. The rule does not ask the due row to
be newer than the last review minute: the tutor's minute row can end minutes
after the last graded card (2026-11-24: 18:31:07 vs 18:34:38 UTC).

This module never imports the display-only ``_review_due``; both parse through
``_review_due_rows``. "Cannot check" mints nothing and logs a warning.
:func:`due_review_clear` runs inside ``_theory_credit``'s fenced poll, so the
lock's poll and the one-minute harvester both mint it.
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard._daycost import day_key
from leetcode_guard._review_due_rows import REVIEW_DUE, latest_rows
from leetcode_guard._theory_finish import theory_row
from leetcode_guard._tutor_minutes import review_minutes
from leetcode_guard._tutor_signed import ModuleKey, signed_rows

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

    from leetcode_guard._ledger import LedgerEntry
    from leetcode_guard._ledger_io import Ledger
    from leetcode_guard._phase import PhaseState

_logger: Final = logging.getLogger(__name__)

PREFIX: Final = "review-clear"
TUTOR_LEDGER: Final = "ledger.json"
Due = dict[ModuleKey, tuple[float, list[int]]]


def clear_id(day: date, unit: str) -> str:
    """``review-clear:<day>:<unit>``: once per unit per day."""
    return f"{PREFIX}:{day_key(day)}:{unit}"


def clear_entry(
    stamp: tuple[date, datetime],
    unit: str,
    *,
    cards: int,
    repair: bool = False,
    key_file: Path | None = None,
) -> LedgerEntry:
    """The signed credit for clearing ``unit``'s reviews on ``stamp``'s day."""
    detail = {"unit": unit, "cards": str(cards)}
    if repair:
        detail["repair"] = "true"
    return theory_row(clear_id(stamp[0], unit), stamp, detail, key_file)


def local_day(at: float) -> date:
    """The local day of a Unix-seconds stamp (the tutor's ``at``)."""
    return datetime.fromtimestamp(at).astimezone().date()


def targets_of(state: PhaseState) -> list[ModuleKey]:
    """The unit's (subject, module) pairs."""
    return [(state.subject, module) for module in state.modules]


def reviewed_on(
    targets: list[ModuleKey], day: date, key_file: Path | None
) -> bool | None:
    """Whether signed review minutes on ``targets`` ended on ``day``.

    ``None`` = the tutor ledger cannot be read.
    """
    rows = signed_rows(TUTOR_LEDGER, key_file=key_file)
    if rows is None:
        return None
    return review_minutes(rows, targets, day=day) > 0


def read_due(targets: list[ModuleKey], key_file: Path | None) -> Due | None:
    """The winning due row of every target; ``None`` (logged) = cannot check."""
    rows = signed_rows(REVIEW_DUE, key_file=key_file, strict=True)
    if rows is None:
        _logger.warning("review clear cannot be checked: %s unreadable", REVIEW_DUE)
        return None
    latest = latest_rows(rows)
    missing = [target for target in targets if target not in latest]
    if missing:
        _logger.warning("review clear cannot be checked: no due row for %s", missing)
        return None
    return {target: latest[target] for target in targets}


def cleared(due: Due, *, day: date, now_ms: int) -> int | None:
    """The unit's card count if every row was written on ``day`` with none due now."""
    for at, times in due.values():
        if local_day(at) != day or any(t <= now_ms for t in times):
            return None
    return sum(len(times) for _, times in due.values())


def due_review_clear(
    ledger: Ledger,
    state: PhaseState,
    *,
    stamp: tuple[date, datetime],
    key_file: Path | None = None,
) -> list[LedgerEntry]:
    """The review-clear credit the current unit earned today, if not minted yet."""
    day, now = stamp
    if (
        state.phase == "none"
        or not state.modules
        or ledger.has(clear_id(day, state.unit))
    ):
        return []
    targets = targets_of(state)
    if not reviewed_on(targets, day, key_file):
        return []
    due = read_due(targets, key_file)
    if due is None:
        return []
    cards = cleared(due, day=day, now_ms=int(now.timestamp() * 1000))
    if cards is None:
        return []
    _logger.info("review clear: %s cleared on %s", state.unit, day_key(day))
    return [clear_entry(stamp, state.unit, cards=cards, key_file=key_file)]
