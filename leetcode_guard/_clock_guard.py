"""Detect a rolled-back system clock.

The cheapest bypass of a day-keyed gate is not editing the ledger -- it is
setting the date back to a day that has already been charged. The gate then
finds ``charge:<today>`` already present and unlocks with no solve, using an
entry it wrote itself, correctly signed. Nothing about the ledger looks wrong.

So the check has to attack the **read** path, not just the write path: an
existing charge for a day that is older than the newest charge on record must
not be honoured. Consulting it only on writes would leave the bypass fully
open.

The cost of being wrong in the strict direction is one escape-hatch use after a
legitimate backwards NTP correction. The cost of being wrong in the permissive
direction is a gate that a date change disables. That trade is not close.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard._daycost import parse_day
from leetcode_guard._ledger import CHARGE

if TYPE_CHECKING:
    from datetime import date

    from leetcode_guard._ledger_io import Ledger

_logger: Final = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClockVerdict:
    """Whether today's date can be believed."""

    trusted: bool
    latest_charged: date | None
    reason: str


def latest_charged_day(ledger: Ledger) -> date | None:
    """The most recent day the gate has charged for.

    Unparsable dates are skipped with an ERROR rather than aborting the scan:
    one bad row must not blind the whole check, which would be a bypass in
    itself.
    """
    days = []
    for entry in ledger.of_kind(CHARGE):
        parsed = parse_day(entry.day)
        if parsed is None:
            _logger.error(
                "ledger entry %s has an unparsable day %r -- ignoring it for the "
                "clock check",
                entry.entry_id,
                entry.day,
            )
            continue
        days.append(parsed)
    return max(days) if days else None


def check_clock(ledger: Ledger, *, day: date) -> ClockVerdict:
    """Decide whether ``day`` is plausible given what has already been charged.

    Args:
        ledger: The loaded ledger.
        day: Today's local date.

    Returns:
        A verdict. ``trusted=False`` means the system clock has moved backwards
        past a day the gate already settled.
    """
    latest = latest_charged_day(ledger)
    if latest is None:
        return ClockVerdict(
            trusted=True, latest_charged=None, reason="nothing charged yet"
        )
    if day < latest:
        _logger.error(
            "system date %s is earlier than the most recently charged day %s -- "
            "refusing to honour an existing charge for today",
            day,
            latest,
        )
        return ClockVerdict(
            trusted=False,
            latest_charged=latest,
            reason=(
                f"The system date ({day}) is earlier than the last day this gate "
                f"settled ({latest}). Fix the clock, or use the escape hatch."
            ),
        )
    return ClockVerdict(
        trusted=True, latest_charged=latest, reason=f"last charged {latest}"
    )
