"""When the progress row is not written, and what a failed write costs.

kuhy decided (2026-11-22) that every gate pays its shutdown bonus in proportion
to progress. ``earned_time`` cannot know this guard's price, so the guard signs
the fact. The row is inert here: nothing this module's rows touch may decide,
charge, credit or lock. Each safety test is named after the rule it pins.
"""

from __future__ import annotations

from dataclasses import replace
import logging
from typing import TYPE_CHECKING

import pytest

from leetcode_guard._gate_progress import (
    apply_progress,
)
from leetcode_guard._gate_state import GateState
from leetcode_guard._ledger_io import Ledger, append
from leetcode_guard.tests._ledger_fixtures import (
    add_charge,
    credits_for,
    ledger_with_credits,
)
from leetcode_guard.tests._progress_fixtures import (
    MONDAY,
    NOW,
    SATURDAY,
    decision_of,
    sign_progress,
)

if TYPE_CHECKING:
    from pathlib import Path

    from leetcode_guard._ledger import LedgerEntry


@pytest.mark.parametrize(
    "flags",
    [{"free_day": True}, {"sick_day": True}, {"focus_day": "some-project"}],
)
def test_a_standing_down_day_gets_no_row(hmac_key: Path, flags: dict):
    """Free, sick and focus days are not gated, so there is nothing to prove."""
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    decision = decision_of(ledger, hmac_key, **flags)

    assert not sign_progress(ledger, decision, hmac_key)
    assert not ledger.of_kind("progress")


def test_a_charged_day_gets_no_row(hmac_key: Path):
    """Full pay comes from the charge, already written."""
    ledger = ledger_with_credits(3, day=MONDAY, key_file=hmac_key)
    add_charge(ledger, MONDAY, key_file=hmac_key)
    decision = decision_of(ledger, hmac_key)

    assert decision.state is GateState.UNLOCKED_ALREADY_CHARGED
    assert not sign_progress(ledger, decision, hmac_key)


def test_a_day_paid_this_moment_gets_no_row(hmac_key: Path):
    """Enough credit means a charge, not a fraction."""
    ledger = ledger_with_credits(3, day=MONDAY, key_file=hmac_key)
    decision = decision_of(ledger, hmac_key)

    assert decision.state is GateState.UNLOCKED_CHARGED_NOW
    assert not sign_progress(ledger, decision, hmac_key)


def test_nothing_done_gets_no_row(hmac_key: Path):
    """done must be at least one: an empty day is not progress."""
    ledger = Ledger()

    assert not sign_progress(ledger, decision_of(ledger, hmac_key), hmac_key)
    assert not ledger.entries


def test_a_rolled_back_clock_gets_no_row(hmac_key: Path):
    """An untrusted date must not sign a fact about a day that is not today."""
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    add_charge(ledger, SATURDAY, key_file=hmac_key)
    decision = decision_of(ledger, hmac_key)

    assert decision.state is GateState.LOCKED_CLOCK_UNTRUSTED
    assert not sign_progress(ledger, decision, hmac_key)
    assert not ledger.of_kind("progress")


def test_the_same_row_is_never_written_twice(hmac_key: Path):
    """Polling again changes nothing and does not rewrite the file."""
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    decision = decision_of(ledger, hmac_key)
    path = hmac_key.parent / "ledger.json"
    assert apply_progress(ledger, decision, path, now=NOW, key_file=hmac_key)
    before = path.read_bytes()

    assert not apply_progress(ledger, decision, path, now=NOW, key_file=hmac_key)
    assert path.read_bytes() == before


def test_more_progress_adds_a_new_row_beside_the_old(hmac_key: Path):
    """Ids carry the numbers, so a second solve is a second row."""
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    path = hmac_key.parent / "ledger.json"
    apply_progress(
        ledger, decision_of(ledger, hmac_key), path, now=NOW, key_file=hmac_key
    )
    more = credits_for(2, day=MONDAY, now=NOW, key_file=hmac_key)
    append(ledger, [replace(e, entry_id=f"extra-{e.entry_id}") for e in more[1:]])

    apply_progress(
        ledger, decision_of(ledger, hmac_key), path, now=NOW, key_file=hmac_key
    )

    assert ledger.has("progress:2026-11-23:1:3")
    assert ledger.has("progress:2026-11-23:2:3")


def test_an_unwritable_ledger_keeps_the_row_in_memory_and_says_so(
    hmac_key: Path, caplog: pytest.LogCaptureFixture
):
    """The credit and the decision stand; the failure is logged, not raised."""
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    decision = decision_of(ledger, hmac_key)
    blocked = hmac_key.parent / "no-such-dir" / "deeper" / "ledger.json"
    hmac_key.parent.joinpath("no-such-dir").write_text("a file, not a directory")

    with caplog.at_level(logging.WARNING):
        wrote = apply_progress(ledger, decision, blocked, now=NOW, key_file=hmac_key)

    assert not wrote
    assert len(ledger.of_kind("credit")) == 1
    assert any(r.levelno >= logging.WARNING for r in caplog.records)


def test_an_unreadable_key_writes_no_unsigned_row(
    tmp_path: Path, hmac_key: Path, caplog: pytest.LogCaptureFixture
):
    """An unsigned row is worthless, and its id would block the signed one."""
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    decision = decision_of(ledger, hmac_key)
    missing = tmp_path / "gone.key"

    with caplog.at_level(logging.WARNING):
        wrote = apply_progress(
            ledger, decision, tmp_path / "ledger.json", now=NOW, key_file=missing
        )

    assert not wrote
    assert not ledger.of_kind("progress")
    assert any(r.levelno >= logging.WARNING for r in caplog.records)


def test_a_failure_building_the_row_never_reaches_the_caller(
    hmac_key: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """Whatever goes wrong inside, the credit stands and a warning is logged."""
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    decision = decision_of(ledger, hmac_key)

    def boom(**_kwargs: object) -> LedgerEntry:
        message = "row builder broke"
        raise ValueError(message)

    monkeypatch.setattr("leetcode_guard._gate_progress.progress_entry", boom)

    with caplog.at_level(logging.WARNING):
        wrote = sign_progress(ledger, decision, hmac_key)

    assert not wrote
    assert len(ledger.of_kind("credit")) == 1
    assert any(r.levelno >= logging.WARNING for r in caplog.records)
