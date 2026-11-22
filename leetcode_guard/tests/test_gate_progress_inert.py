"""The progress row is inert: it moves no decision, balance, debt, clock or lock.

kuhy decided (2026-11-22) that every gate pays its shutdown bonus in proportion
to progress. ``earned_time`` cannot know this guard's price, so the guard signs
the fact. The row is inert here: nothing this module's rows touch may decide,
charge, credit or lock. Each safety test is named after the rule it pins.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from leetcode_guard._balance import compute_balance
from leetcode_guard._clock_guard import check_clock
from leetcode_guard._debt import compute_debt
from leetcode_guard._gate import DayContext, decide
from leetcode_guard._gate_progress import (
    apply_progress,
)
from leetcode_guard._gate_state import GateState
from leetcode_guard._ledger import sign
from leetcode_guard._ledger_entries import progress_entry
from leetcode_guard._ledger_io import Ledger, append, load_ledger
from leetcode_guard.tests._progress_fixtures import (
    FRIDAY,
    MONDAY,
    NOW,
    SATURDAY,
    TUESDAY,
    decision_of,
    ledgers,
    never_free,
    with_progress,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_progress_rows_change_no_decision_balance_debt_or_clock_verdict(hmac_key: Path):
    """The inert-row rule: identical answers with and without the rows."""
    contexts = [
        DayContext(),
        DayContext(free_day=True),
        DayContext(workday_penalty=True),
    ]
    for ledger in ledgers(hmac_key):
        twin = with_progress(ledger, hmac_key)
        for day in (MONDAY, TUESDAY, FRIDAY, SATURDAY):
            for context in contexts:
                args = {
                    "day": day,
                    "now": NOW,
                    "key_file": hmac_key,
                    "context": context,
                }
                assert decide(twin, **args) == decide(ledger, **args)
            assert check_clock(twin, day=day) == check_clock(ledger, day=day)
            assert compute_debt(twin, day=day, is_free=never_free, start=FRIDAY) == (
                compute_debt(ledger, day=day, is_free=never_free, start=FRIDAY)
            )
        assert compute_balance(twin) == compute_balance(ledger)


def test_no_progress_row_can_unlock_anything(hmac_key: Path):
    """Only progress rows for today (even one claiming amount 999) stay LOCKED."""
    ledger = Ledger()
    forged = sign(
        replace(
            progress_entry(
                for_day=MONDAY, done=3, target=3, now=NOW, key_file=hmac_key
            ),
            amount=999,
        ),
        key_file=hmac_key,
    )
    append(
        ledger,
        [
            progress_entry(
                for_day=MONDAY, done=3, target=3, now=NOW, key_file=hmac_key
            ),
            replace(forged, entry_id="progress:2026-11-23:3:4"),
        ],
    )

    decision = decision_of(ledger, hmac_key)

    assert decision.state is GateState.LOCKED_INSUFFICIENT
    assert decision.balance.available == 0
    assert decision.charge is None


def test_deleting_the_ledger_earns_no_progress(hmac_key: Path):
    """``rm ledger.json`` leaves an empty ledger, which has no progress to sign."""
    path = hmac_key.parent / "ledger.json"
    ledger = load_ledger(path, key_file=hmac_key)

    assert not apply_progress(
        ledger, decision_of(ledger, hmac_key), path, now=NOW, key_file=hmac_key
    )
    assert not path.exists()
