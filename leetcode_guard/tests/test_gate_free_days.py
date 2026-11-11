"""Gate decisions on free days and workday-penalty days."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._gate import (
    DayContext,
    GateState,
)
from leetcode_guard._ledger_io import Ledger
from leetcode_guard.tests._gate_fixtures import decide_with
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    SATURDAY,
    TUESDAY,
    add_charge,
    ledger_with_credits,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_a_free_day_unlocks_without_spending_credit(hmac_key: Path):
    """A day off is not paid for out of the balance."""
    ledger = ledger_with_credits(2, day=MONDAY, key_file=hmac_key)

    decision = decide_with(ledger, hmac_key, DayContext(free_day=True))

    assert decision.state is GateState.UNLOCKED_FREE_DAY
    assert not decision.locked
    assert decision.charge is None
    assert decision.needed == 0


def test_a_free_day_unlocks_even_with_no_credit_at_all(hmac_key: Path):
    """A free day unlocks with an empty ledger."""
    decision = decide_with(Ledger(), hmac_key, DayContext(free_day=True))

    assert decision.state is GateState.UNLOCKED_FREE_DAY
    assert not decision.locked


def test_a_free_day_does_not_override_an_untrusted_clock(hmac_key: Path):
    """A rolled-back clock makes the claimed date untrustworthy too."""
    ledger = Ledger()
    add_charge(ledger, TUESDAY, key_file=hmac_key)

    decision = decide_with(ledger, hmac_key, DayContext(free_day=True))

    assert decision.state is GateState.LOCKED_CLOCK_UNTRUSTED
    assert decision.locked


def test_without_a_free_day_the_normal_rules_still_apply(hmac_key: Path):
    """free_day=False leaves an empty ledger locked."""
    decision = decide_with(Ledger(), hmac_key, DayContext(free_day=False))

    assert decision.state is GateState.LOCKED_INSUFFICIENT


def test_a_workday_penalty_removes_tuesdays_discount(hmac_key: Path):
    """A workday penalty raises Tuesday's cost to 2."""
    decision = decide_with(
        Ledger(), hmac_key, DayContext(workday_penalty=True), day=TUESDAY
    )

    assert decision.cost == 2
    assert "Tuesday costs 2" in decision.reason


def test_no_workday_penalty_keeps_tuesdays_discount(hmac_key: Path):
    """Without the penalty Tuesday still costs 1."""
    decision = decide_with(
        Ledger(), hmac_key, DayContext(workday_penalty=False), day=TUESDAY
    )

    assert decision.cost == 1


def test_a_workday_penalty_on_an_already_doubled_day_changes_nothing(
    hmac_key: Path,
):
    """The penalty does not push a 2-cost Saturday any higher."""
    decision = decide_with(
        Ledger(), hmac_key, DayContext(workday_penalty=True), day=SATURDAY
    )

    assert decision.cost == 2
    assert decision.locked
