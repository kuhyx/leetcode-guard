"""The one-off repair of a review clear the live rule missed (2026-11-24).

kuhy cleared every due prefix-sums card on 2026-11-24 and got no credit: the
rule did not exist yet (``_review_clear``). This mints that day's
``review-clear:<day>:<unit>`` through the same entry builder, with
``detail.repair: "true"``, only on signed evidence:

* the tutor's signed review-minute rows on the unit's modules that day;
* ``charge:<day>`` in this ledger (the day was gated and settled);
* the newest signed due row of every module of the unit, written after the
  day ended, with every card due after the day ended.

Never a hand-written ledger row; a second run finds the row and writes nothing.
Days after the fix use only the live rule.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from enum import Enum
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard._curriculum import load_curriculum
from leetcode_guard._daycost import day_key
from leetcode_guard._ledger_io import append
from leetcode_guard._review_clear import (
    clear_entry,
    clear_id,
    read_due,
    reviewed_on,
)

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

    from leetcode_guard._ledger_io import Ledger
    from leetcode_guard._tutor_signed import ModuleKey

_logger: Final = logging.getLogger(__name__)


class Repair(Enum):
    """What one repair run did."""

    MINTED = "minted"
    ALREADY = "already minted"
    REFUSED = "refused"


def _targets(unit_id: str) -> list[ModuleKey] | None:
    """The unit's (subject, module) pairs from the curriculum, or ``None``."""
    curriculum = load_curriculum()
    units = curriculum.units if curriculum is not None else ()
    unit = next((u for u in units if u.unit_id == unit_id and u.modules), None)
    return None if unit is None else [(unit.subject, m) for m in unit.modules]


def _evidence(
    ledger: Ledger, day: date, targets: list[ModuleKey], key_file: Path | None
) -> int | None:
    """The unit's card count when every piece of evidence holds, else ``None``."""
    if not ledger.has(f"charge:{day_key(day)}"):
        _logger.warning("repair: no charge:%s", day_key(day))
        return None
    if not reviewed_on(targets, day, key_file):
        _logger.warning("repair: no signed review of %s on %s", targets, day_key(day))
        return None
    due = read_due(targets, key_file)
    if due is None:
        return None
    end = datetime.combine(day + timedelta(days=1), time()).astimezone().timestamp()
    for at, times in due.values():
        if at < end or any(t < end * 1000 for t in times):
            _logger.warning("repair: a due row does not put every card after the day")
            return None
    return sum(len(times) for _, times in due.values())


def repair_review_clear(
    ledger: Ledger,
    *,
    day: date,
    unit: str,
    now: datetime,
    key_file: Path | None = None,
) -> Repair:
    """Mint ``review-clear:<day>:<unit>`` into ``ledger`` on signed evidence."""
    if ledger.has(clear_id(day, unit)):
        return Repair.ALREADY
    targets = _targets(unit)
    if targets is None:
        _logger.warning("repair: unit %s has no tutor modules", unit)
        return Repair.REFUSED
    cards = _evidence(ledger, day, targets, key_file)
    if cards is None:
        return Repair.REFUSED
    entry = clear_entry((day, now), unit, cards=cards, repair=True, key_file=key_file)
    append(ledger, [entry])
    return Repair.MINTED
