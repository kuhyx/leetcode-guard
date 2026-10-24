"""Today's verdict, with the lookups :func:`decide` refuses to do itself.

``decide`` is pure: it takes the free-day and sick-day flags and the debt
position as arguments so it can be tested as a table. Every real caller --
the timer run, the poll loop, ``--status``, ``--check`` -- needs the same
lookups first, and this is the one place that does them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import freedays

from leetcode_guard._debt import NO_DEBT, compute_debt
from leetcode_guard._gate import GateDecision, decide
from leetcode_guard._sick import leetcode_stands_down
from leetcode_guard._workday_penalty import workday_penalty_for

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
    """Look up the free-day and sick-day pools and the debt, then decide.

    "Sick" means this gate stands down: a sick day that keeps ``leetcode``
    is an ordinary day here, for today's verdict and for the debt alike.

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
        NO_DEBT
        if demo
        else compute_debt(
            ledger,
            day=day,
            is_free=freedays.is_free_day,
            is_sick=leetcode_stands_down,
        )
    )
    return decide(
        ledger,
        day=day,
        now=now,
        key_file=key_file,
        free_day=freedays.is_free_day(day),
        debt=debt,
        workday_penalty=workday_penalty_for(day),
        sick_day=leetcode_stands_down(day),
    )


def gate_off(day: date) -> bool:
    """Whether this gate stands down on ``day``: free, or sick without leetcode.

    The same two flags :func:`decide_today` hands ``decide``, asked live. A
    stood-down day has no price and no charge, so the bonus consumers let one
    verified solve earn on it (earned_time 0.18.0 ``gate_off``); on every
    other day only the charge that pays the full price does.
    """
    return freedays.is_free_day(day) or leetcode_stands_down(day)
