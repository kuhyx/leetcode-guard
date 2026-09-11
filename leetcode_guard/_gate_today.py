"""Today's verdict, with the two lookups :func:`decide` refuses to do itself.

``decide`` is pure: it takes the free-day flag and the debt position as
arguments so it can be tested as a table. Every real caller -- the timer run,
the poll loop, ``--status``, ``--check`` -- needs the same two lookups first,
and this is the one place that does them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import freedays

from leetcode_guard._debt import NO_DEBT, compute_debt
from leetcode_guard._gate import GateDecision, decide

if TYPE_CHECKING:
    from datetime import date, datetime
    from pathlib import Path

    from leetcode_guard._ledger_io import Ledger


def decide_today(
    ledger: Ledger,
    *,
    day: date,
    now: datetime,
    key_file: Path | None = None,
    demo: bool = False,
) -> GateDecision:
    """Look up the free-day pool and the debt, then decide.

    Args:
        ledger: The loaded ledger.
        day: Today's local date.
        now: Current time, for stamping a new charge.
        key_file: HMAC key override, for tests.
        demo: The demo deletes its ledger on every run, so a derived debt
            there would be every day since the epoch. It shows no debt.

    Returns:
        The decision. Nothing is written.
    """
    debt = (
        NO_DEBT if demo else compute_debt(ledger, day=day, is_free=freedays.is_free_day)
    )
    return decide(
        ledger,
        day=day,
        now=now,
        key_file=key_file,
        free_day=freedays.is_free_day(day),
        debt=debt,
    )
