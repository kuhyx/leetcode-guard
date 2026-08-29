"""Tests for the gate decision and the clock guard."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from leetcode_guard._clock_guard import check_clock, latest_charged_day
from leetcode_guard._gate import (
    GateState,
    apply_decision,
    decide,
    settle_day,
)
from leetcode_guard._ledger import SOURCE_ESCAPE, LedgerEntry
from leetcode_guard._ledger_io import Ledger, append, load_ledger
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    NOW,
    SATURDAY,
    TUESDAY,
    add_charge,
    ledger_with_credits,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_enough_credit_charges_the_day(hmac_key: Path):
    ledger = ledger_with_credits(2, day=MONDAY, key_file=hmac_key)

    decision = decide(ledger, day=MONDAY, now=NOW, key_file=hmac_key)

    assert decision.state is GateState.UNLOCKED_CHARGED_NOW
    assert not decision.locked
    assert decision.charge is not None
    assert decision.needed == 0


def test_an_existing_charge_short_circuits(hmac_key: Path):
    ledger = Ledger()
    add_charge(ledger, MONDAY, key_file=hmac_key)

    decision = decide(ledger, day=MONDAY, now=NOW, key_file=hmac_key)

    assert decision.state is GateState.UNLOCKED_ALREADY_CHARGED
    assert decision.charge is None


def test_too_little_credit_locks(hmac_key: Path):
    decision = decide(Ledger(), day=MONDAY, now=NOW, key_file=hmac_key)

    assert decision.state is GateState.LOCKED_INSUFFICIENT
    assert decision.locked
    assert decision.needed == 1
    assert decision.charge is None


def test_the_weekend_shortfall_is_reported_correctly(hmac_key: Path):
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)

    decision = decide(ledger, day=SATURDAY, now=NOW, key_file=hmac_key)

    assert decision.cost == 2
    assert decision.needed == 1
    assert "Saturday costs 2" in decision.reason


def test_a_rolled_back_clock_refuses_to_honour_an_existing_charge(
    hmac_key: Path, caplog
):
    """The cheapest bypass: set the date back to a settled day and the
    already-charged shortcut fires with no solve."""
    ledger = Ledger()
    add_charge(ledger, TUESDAY, key_file=hmac_key)
    add_charge(ledger, MONDAY, key_file=hmac_key)

    with caplog.at_level(logging.ERROR):
        decision = decide(ledger, day=MONDAY, now=NOW, key_file=hmac_key)

    assert decision.state is GateState.LOCKED_CLOCK_UNTRUSTED
    assert decision.locked
    assert "earlier than" in decision.reason
    assert any(record.levelno == logging.ERROR for record in caplog.records)


def test_the_clock_check_runs_before_the_charge_shortcut(hmac_key: Path):
    """Ordering matters: the shortcut would otherwise fire underneath it."""
    ledger = ledger_with_credits(5, day=MONDAY, key_file=hmac_key)
    add_charge(ledger, TUESDAY, key_file=hmac_key)
    add_charge(ledger, MONDAY, key_file=hmac_key)

    assert decide(ledger, day=MONDAY, now=NOW, key_file=hmac_key).state is (
        GateState.LOCKED_CLOCK_UNTRUSTED
    )


def test_the_same_day_as_the_latest_charge_is_still_trusted(hmac_key: Path):
    ledger = Ledger()
    add_charge(ledger, MONDAY, key_file=hmac_key)

    assert check_clock(ledger, day=MONDAY).trusted


def test_an_empty_ledger_trusts_the_clock():
    verdict = check_clock(Ledger(), day=MONDAY)

    assert verdict.trusted
    assert verdict.latest_charged is None
    assert "nothing charged yet" in verdict.reason


def test_latest_charged_day_ignores_unparsable_dates(hmac_key: Path, caplog):
    """One bad row must not blind the whole check -- that would be a bypass."""
    ledger = Ledger()
    add_charge(ledger, MONDAY, key_file=hmac_key)
    append(ledger, [LedgerEntry("charge:junk", "charge", "not-a-date", "", 1)])

    with caplog.at_level(logging.ERROR):
        latest = latest_charged_day(ledger)

    assert latest == MONDAY
    assert any("unparsable day" in record.message for record in caplog.records)


def test_apply_decision_persists_the_charge(tmp_path: Path, hmac_key: Path):
    path = tmp_path / "ledger.json"
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    decision = decide(ledger, day=MONDAY, now=NOW, key_file=hmac_key)

    assert apply_decision(ledger, decision, path)
    assert load_ledger(path, key_file=hmac_key).has("charge:2026-08-10")


def test_apply_decision_writes_nothing_for_a_locked_decision(
    tmp_path: Path, hmac_key: Path
):
    path = tmp_path / "ledger.json"
    decision = decide(Ledger(), day=MONDAY, now=NOW, key_file=hmac_key)

    assert not apply_decision(Ledger(), decision, path)
    assert not path.exists()


def test_settle_day_forgives_a_day_and_leaves_the_debt(tmp_path: Path, hmac_key: Path):
    """An escaped day is forgiven, not free: the balance goes negative and the
    next day still costs full price."""
    path = tmp_path / "ledger.json"
    ledger = Ledger()

    assert settle_day(
        ledger,
        day=MONDAY,
        now=NOW,
        source=SOURCE_ESCAPE,
        path=path,
        key_file=hmac_key,
    )

    monday = decide(ledger, day=MONDAY, now=NOW, key_file=hmac_key)
    tuesday = decide(ledger, day=TUESDAY, now=NOW, key_file=hmac_key)

    assert monday.state is GateState.UNLOCKED_ALREADY_CHARGED
    assert monday.balance.available == -1
    assert tuesday.state is GateState.LOCKED_INSUFFICIENT
    assert tuesday.needed == 2
    assert ledger.entries["charge:2026-08-10"].detail["source"] == SOURCE_ESCAPE
