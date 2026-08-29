"""Continued from :mod:`leetcode_guard.tests.test_gate`, split for the 250-line cap."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from leetcode_guard._clock_guard import check_clock
from leetcode_guard._constants import GATE_START_DATE
from leetcode_guard._gate import (
    GateState,
    apply_decision,
    decide,
    settle_day,
)
from leetcode_guard._ledger import SOURCE_ESCAPE
from leetcode_guard._ledger_io import Ledger, save_ledger
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    NOW,
    add_charge,
    ledger_with_credits,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_settle_day_is_idempotent(tmp_path: Path, hmac_key: Path):
    path = tmp_path / "ledger.json"
    ledger = Ledger()

    assert settle_day(
        ledger, day=MONDAY, now=NOW, source=SOURCE_ESCAPE, path=path, key_file=hmac_key
    )
    assert not settle_day(
        ledger, day=MONDAY, now=NOW, source=SOURCE_ESCAPE, path=path, key_file=hmac_key
    )


def test_a_far_future_date_is_trusted(hmac_key: Path):
    """Only backwards movement is suspicious; a forward jump just means time
    passed while the PC was off."""
    ledger = Ledger()
    add_charge(ledger, MONDAY, key_file=hmac_key)

    assert check_clock(ledger, day=date(2027, 1, 1)).trusted


def test_save_failure_makes_apply_decision_report_false(tmp_path: Path, hmac_key: Path):
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    decision = decide(ledger, day=MONDAY, now=NOW, key_file=hmac_key)

    assert not apply_decision(ledger, decision, blocker / "ledger.json")


def test_settle_day_reports_a_failed_save(tmp_path: Path, hmac_key: Path):
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")

    assert not settle_day(
        Ledger(),
        day=MONDAY,
        now=NOW,
        source=SOURCE_ESCAPE,
        path=blocker / "ledger.json",
        key_file=hmac_key,
    )


def test_saving_an_empty_ledger_still_works(tmp_path: Path):
    assert save_ledger(tmp_path / "ledger.json", Ledger())


def test_the_gate_is_inert_before_its_start_date(hmac_key: Path, gate_starts):
    """Installed but not yet in force. systemd cannot express "not before date
    X", so the start date lives here where --status and MCP can see it."""
    before = GATE_START_DATE - timedelta(days=1)

    decision = decide(Ledger(), day=before, now=NOW, key_file=hmac_key)

    assert decision.state is GateState.UNLOCKED_NOT_STARTED
    assert not decision.locked
    assert decision.charge is None
    assert str(GATE_START_DATE) in decision.reason


def test_the_gate_locks_on_its_start_date(hmac_key: Path, gate_starts):
    decision = decide(Ledger(), day=GATE_START_DATE, now=NOW, key_file=hmac_key)

    assert decision.state is GateState.LOCKED_INSUFFICIENT
    assert decision.locked


def test_the_start_date_never_masks_a_rolled_back_clock(hmac_key: Path, gate_starts):
    """Ordering matters: if the start-date check ran first, setting the date
    back to July would re-enter the inert state and disable the gate forever."""
    ledger = Ledger()
    add_charge(ledger, GATE_START_DATE + timedelta(days=3), key_file=hmac_key)

    decision = decide(
        ledger, day=GATE_START_DATE - timedelta(days=10), now=NOW, key_file=hmac_key
    )

    assert decision.state is GateState.LOCKED_CLOCK_UNTRUSTED
    assert decision.locked


def test_an_inert_day_is_never_charged(tmp_path: Path, hmac_key: Path, gate_starts):
    """Nothing is spent while the gate is not in force."""
    path = tmp_path / "ledger.json"
    ledger = ledger_with_credits(2, day=MONDAY, key_file=hmac_key)
    decision = decide(
        ledger, day=GATE_START_DATE - timedelta(days=1), now=NOW, key_file=hmac_key
    )

    assert not apply_decision(ledger, decision, path)
    assert decision.balance.available == 2
