"""User stories for the missed-day debt. Continued from :mod:`test_scenarios`.

The rule these pin: a day the gate never charged is owed at its price, and
every day costs one credit more until it is repaid. Written as the user would
tell them, so that if one has to change, the feature has changed.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

import freedays

from leetcode_guard._daycost import day_cost
from leetcode_guard._gate import GateState, settle_day
from leetcode_guard._gate_today import decide_today
from leetcode_guard._ledger import SOURCE_ESCAPE
from leetcode_guard._ledger_entries import credit_entry
from leetcode_guard._ledger_io import Ledger, append
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    NOW,
    SATURDAY,
    THURSDAY,
    WEDNESDAY,
    add_charge,
    credits_for,
    submission,
)
from leetcode_guard.tests.test_scenarios import run_day

if TYPE_CHECKING:
    from pathlib import Path

NEXT_THURSDAY = THURSDAY + timedelta(days=7)
"""Back from a week away: Thursday to Wednesday missed, seven days."""


def solve(ledger: Ledger, count: int, *, day: date, key_file: Path) -> None:
    """``count`` fresh solves on ``day``, with ids that cannot collide with
    :func:`credits_for`'s or with an earlier day's."""
    append(
        ledger,
        [
            credit_entry(
                submission(f"{day.isoformat()}-{index}"),
                day=day,
                now=NOW,
                key_file=key_file,
            )
            for index in range(count)
        ],
    )


def a_week_away(hmac_key: Path) -> Ledger:
    """Monday to Wednesday paid, then nothing until the following Thursday."""
    ledger = Ledger()
    append(ledger, credits_for(3, day=MONDAY, now=NOW, key_file=hmac_key))
    for day in (MONDAY, MONDAY + timedelta(days=1), WEDNESDAY):
        add_charge(ledger, day, key_file=hmac_key)
    return ledger


def test_a_week_away_is_owed_at_the_price_of_each_missed_day(
    hmac_key: Path, debt_starts
):
    """Thu, Fri, Mon, Tue, Wed at 1 and Sat, Sun at 2: nine credits, and the
    first day back costs 2 instead of 1."""
    debt_starts(MONDAY)
    ledger = a_week_away(hmac_key)

    decision = decide_today(ledger, day=NEXT_THURSDAY, now=NOW, key_file=hmac_key)

    assert decision.debt.missed_days == 7
    assert decision.debt.outstanding == 9
    assert decision.cost == 2
    assert decision.state is GateState.LOCKED_INSUFFICIENT
    assert decision.needed == 2
    assert "Thursday costs 2 (1 +1 debt)" in decision.reason


def test_one_solve_on_a_surcharged_weekday_still_locks(hmac_key: Path, debt_starts):
    debt_starts(MONDAY)
    ledger = a_week_away(hmac_key)
    solve(ledger, 1, day=NEXT_THURSDAY, key_file=hmac_key)

    decision = decide_today(ledger, day=NEXT_THURSDAY, now=NOW, key_file=hmac_key)

    assert decision.state is GateState.LOCKED_INSUFFICIENT
    assert decision.needed == 1


def test_two_solves_on_a_surcharged_weekday_unlock_and_repay_one(
    tmp_path: Path, hmac_key: Path, debt_starts
):
    debt_starts(MONDAY)
    ledger = a_week_away(hmac_key)
    solve(ledger, 2, day=NEXT_THURSDAY, key_file=hmac_key)
    path = tmp_path / "ledger.json"

    decision = decide_today(ledger, day=NEXT_THURSDAY, now=NOW, key_file=hmac_key)
    assert decision.state is GateState.UNLOCKED_CHARGED_NOW
    assert decision.charge is not None
    assert decision.charge.amount == 2
    assert decision.charge.detail["surcharge"] == "1"
    run_day(ledger, NEXT_THURSDAY, path, hmac_key, debt=decision.debt)

    tomorrow = decide_today(
        ledger, day=NEXT_THURSDAY + timedelta(days=1), now=NOW, key_file=hmac_key
    )
    assert tomorrow.debt.repaid == 1
    assert tomorrow.debt.outstanding == 8
    assert tomorrow.cost == 2


def test_paying_one_extra_a_day_gets_back_on_track_and_the_price_drops(
    tmp_path: Path, hmac_key: Path, debt_starts
):
    """Nine credits of debt, one repaid per day: nine surcharged days, then
    the tenth costs the ordinary price again."""
    debt_starts(MONDAY)
    ledger = a_week_away(hmac_key)
    path = tmp_path / "ledger.json"
    surcharged_days = 0
    day = NEXT_THURSDAY
    for _ in range(20):
        decision = decide_today(ledger, day=day, now=NOW, key_file=hmac_key)
        if not decision.debt.outstanding:
            break
        surcharged_days += 1
        solve(ledger, decision.cost, day=day, key_file=hmac_key)
        run_day(ledger, day, path, hmac_key, debt=decision.debt)
        day += timedelta(days=1)

    assert surcharged_days == 9
    assert decision.debt.outstanding == 0
    assert decision.cost == day_cost(day)
    assert "debt" not in decision.reason


def test_a_free_day_inside_the_gap_is_not_owed(hmac_key: Path, debt_starts):
    debt_starts(MONDAY)
    ledger = a_week_away(hmac_key)
    freedays.mark(SATURDAY, now=THURSDAY)

    decision = decide_today(ledger, day=NEXT_THURSDAY, now=NOW, key_file=hmac_key)

    assert decision.debt.missed_days == 6
    assert decision.debt.outstanding == 7


def test_a_free_day_today_pauses_the_debt_without_repaying_it(
    hmac_key: Path, debt_starts
):
    debt_starts(MONDAY)
    ledger = a_week_away(hmac_key)
    freedays.mark(NEXT_THURSDAY, now=THURSDAY)

    decision = decide_today(ledger, day=NEXT_THURSDAY, now=NOW, key_file=hmac_key)

    assert decision.state is GateState.UNLOCKED_FREE_DAY
    assert decision.charge is None
    assert decision.debt.outstanding == 9


def test_an_escaped_day_settles_itself_but_repays_nothing(
    tmp_path: Path, hmac_key: Path, debt_starts
):
    """The hatch forgives the day it is pulled on -- that day is charged, so
    it is not owed -- but it is no way to pay the rest down."""
    debt_starts(MONDAY)
    ledger = a_week_away(hmac_key)
    path = tmp_path / "ledger.json"
    settle_day(
        ledger,
        day=NEXT_THURSDAY,
        now=NOW,
        source=SOURCE_ESCAPE,
        path=path,
        key_file=hmac_key,
    )

    tomorrow = decide_today(
        ledger, day=NEXT_THURSDAY + timedelta(days=1), now=NOW, key_file=hmac_key
    )

    assert tomorrow.debt.missed_days == 7
    assert tomorrow.debt.repaid == 0
    assert tomorrow.debt.outstanding == 9
    assert tomorrow.balance.available == -1
    assert tomorrow.needed == 2 + 1
