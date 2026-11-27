"""The ``status.lock`` block's inputs: ``unpaid`` and the review read.

``unpaid`` is "today still needs credits"; the review is asked the way the
lock's ``PhaseReader`` asks it (``_snapshot_lock.read_review``).
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _snapshot_lock
from leetcode_guard._gate import DayContext, GateState, decide
from leetcode_guard._ledger_io import Ledger
from leetcode_guard._review_due import UNKNOWN, DueRead, DueStatus
from leetcode_guard._snapshot_lock import lock_block, read_review
from leetcode_guard._status import verdict_of
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    NOW,
    add_charge,
    ledger_with_credits,
)
from leetcode_guard.tests._phase_fixtures import NONE, SOLVE, THEORY
from leetcode_guard.tests._review_first_fixtures import (
    DUE,
    SOLVE_R,
    T_MS,
    write_module_due,
)
from leetcode_guard.tests.test_snapshot_lock import LOCKED, source

if TYPE_CHECKING:
    from pathlib import Path


def test_a_locked_day_is_unpaid():
    """Not enough credit: today still needs paying."""
    assert lock_block(verdict_of(LOCKED), source())["unpaid"] is True


def test_a_day_the_credits_cover_is_not_unpaid(hmac_key: Path):
    """Charged now (the charge not yet written) needs nothing more."""
    ledger = ledger_with_credits(5, day=MONDAY, key_file=hmac_key)
    decision = decide(ledger, day=MONDAY, now=NOW, key_file=hmac_key)
    assert decision.state is GateState.UNLOCKED_CHARGED_NOW

    assert lock_block(verdict_of(decision), source())["unpaid"] is False


def test_an_already_charged_day_is_not_unpaid(hmac_key: Path):
    """Settled by an earlier run."""
    ledger = ledger_with_credits(5, day=MONDAY, key_file=hmac_key)
    add_charge(ledger, MONDAY, key_file=hmac_key)
    decision = decide(ledger, day=MONDAY, now=NOW, key_file=hmac_key)
    assert decision.state is GateState.UNLOCKED_ALREADY_CHARGED

    assert lock_block(verdict_of(decision), source())["unpaid"] is False


@pytest.mark.parametrize(
    "context",
    [DayContext(free_day=True), DayContext(sick_day=True)],
    ids=["free", "sick"],
)
def test_a_stood_down_day_is_not_unpaid(context: DayContext):
    """Free and sick days owe nothing."""
    decision = decide(Ledger(), day=MONDAY, now=NOW, context=context)

    assert lock_block(verdict_of(decision), source())["unpaid"] is False


def test_a_day_before_the_gate_starts_is_not_unpaid(gate_starts):
    """Not in force yet."""
    decision = decide(Ledger(), day=gate_starts - timedelta(days=1), now=NOW)
    assert decision.state is GateState.UNLOCKED_NOT_STARTED

    assert lock_block(verdict_of(decision), source())["unpaid"] is False


def test_the_review_is_read_only_on_a_solve_unit_with_modules(hmac_key: Path):
    """THEORY, no phase and a SOLVE unit without modules ask nothing."""
    for view in (THEORY, NONE, SOLVE):
        assert read_review(view, at=NOW, key_file=hmac_key) is None


def test_due_cards_need_a_tutor_to_open_like_the_lock(
    monkeypatch: pytest.MonkeyPatch, hmac_key: Path
):
    """No launcher: the lock shows the SOLVE rows, so the snapshot does too."""
    write_module_due(hmac_key, [T_MS - 1000, T_MS - 10])
    monkeypatch.setattr(_snapshot_lock, "find_tutor", lambda: "/x/tutor")
    due = read_review(SOLVE_R, at=NOW, key_file=hmac_key)
    monkeypatch.setattr(_snapshot_lock, "find_tutor", lambda: None)

    assert due == DueRead(DueStatus.DUE, 2, DUE.target)
    assert read_review(SOLVE_R, at=NOW, key_file=hmac_key) is UNKNOWN


def test_a_solve_unit_with_nothing_due_is_clear(
    monkeypatch: pytest.MonkeyPatch, hmac_key: Path
):
    """Cards due later are not due now; no tutor is asked for."""
    write_module_due(hmac_key, [T_MS + 60_000])
    monkeypatch.setattr(
        _snapshot_lock, "find_tutor", lambda: pytest.fail("asked for a tutor")
    )

    assert read_review(SOLVE_R, at=NOW, key_file=hmac_key).status is DueStatus.CLEAR
