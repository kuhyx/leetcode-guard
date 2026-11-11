"""Debt never surcharges Tue-Thu. Continued from :mod:`test_debt`."""

from __future__ import annotations

from datetime import timedelta

import pytest

from leetcode_guard import _gate_today
from leetcode_guard._debt import Debt, cost_phrase
from leetcode_guard._ledger_io import Ledger
from leetcode_guard.tests._ledger_fixtures import MONDAY, NOW, TUESDAY, WEDNESDAY

NEXT_MONDAY = MONDAY + timedelta(days=7)


def test_tuesday_to_thursday_never_carry_the_surcharge():
    """Tuesday to Thursday carry no debt surcharge; Friday does."""
    owing = Debt(owed=30, repaid=0, missed_days=20)

    assert cost_phrase(TUESDAY, 2, owing) == "Tuesday costs 2"
    assert owing.surcharge_on(WEDNESDAY) == 0
    assert owing.surcharge_on(WEDNESDAY + timedelta(days=1)) == 0  # Thursday
    assert owing.surcharge_on(WEDNESDAY + timedelta(days=2)) == 1  # Friday


@pytest.mark.usefixtures("hmac_key")
def test_decide_today_surcharges_a_monday_while_debt_is_outstanding(debt_starts):
    """A Monday costs one extra solve while earlier debt is unpaid."""
    debt_starts(MONDAY)

    decision = _gate_today.decide_today(Ledger(), day=NEXT_MONDAY, now=NOW)

    assert decision.cost == 2
