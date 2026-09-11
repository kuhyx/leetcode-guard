"""Continued from :mod:`test_viewmodel`: the debt on the lock surface."""

from __future__ import annotations

from datetime import timedelta

from leetcode_guard._debt import Debt
from leetcode_guard._gate import decide
from leetcode_guard._ledger_io import Ledger
from leetcode_guard._viewmodel import build_viewmodel
from leetcode_guard.tests._ledger_fixtures import MONDAY, NOW
from leetcode_guard.tests.test_viewmodel import (
    CHECKED_AT,
    OK_PROBE,
    SIGNED_OUT,
    pool_of,
)

OWING = Debt(owed=9, repaid=2, missed_days=7)


def test_the_surface_explains_a_surcharged_price(hmac_key):
    """A quota that silently doubled reads as a bug, so the balance line
    spells the surcharge out and a note says where it came from."""
    decision = decide(Ledger(), day=MONDAY, now=NOW, key_file=hmac_key, debt=OWING)

    model = build_viewmodel(
        decision, pool_of(), SIGNED_OUT, OK_PROBE, checked_at=CHECKED_AT, limit=10
    )

    assert model.headline == "Solve 2 LeetCode problems to unlock"
    assert "Monday costs 2 (1 +1 debt)" in model.balance_line
    assert any(
        note.startswith("Debt: 7 credits outstanding (7 missed days owed 9, 2 repaid)")
        for note in model.notes
    )


def test_no_debt_note_when_on_track(hmac_key):
    decision = decide(
        Ledger(), day=MONDAY + timedelta(days=1), now=NOW, key_file=hmac_key
    )

    model = build_viewmodel(
        decision, pool_of(), SIGNED_OUT, OK_PROBE, checked_at=CHECKED_AT, limit=10
    )

    assert "Tuesday costs 1" in model.balance_line
    assert not any("Debt" in note for note in model.notes)
