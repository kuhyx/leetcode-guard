"""Tests for the missed-day debt: derived from calendar and ledger, never stored."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

import pytest

from leetcode_guard._debt import (
    NO_DEBT,
    Debt,
    compute_debt,
    cost_phrase,
    debt_line,
    debt_summary,
)
from leetcode_guard._ledger_entries import charge_entry
from leetcode_guard._ledger_io import Ledger, append
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    NOW,
    SATURDAY,
    SUNDAY,
    TUESDAY,
    WEDNESDAY,
    add_charge,
)

if TYPE_CHECKING:
    from pathlib import Path

NEXT_MONDAY = MONDAY + timedelta(days=7)


def never_free(_day: date) -> bool:
    """A free-day pool that never grants a free day."""
    return False


@pytest.mark.usefixtures("hmac_key")
def test_every_uncharged_day_in_the_window_is_owed_at_its_price():
    """Monday to Sunday with nothing charged: five weekdays and a weekend."""
    debt = compute_debt(Ledger(), day=NEXT_MONDAY, is_free=never_free, start=MONDAY)

    assert debt.missed_days == 7
    assert debt.owed == 5 + 2 + 2
    assert debt.repaid == 0
    assert debt.outstanding == 9
    assert debt.surcharge_on(MONDAY) == 1
    assert debt.surcharge_on(TUESDAY) == 0


def test_today_is_not_owed_while_it_is_still_today():
    """The current day is never counted as missed."""
    debt = compute_debt(Ledger(), day=MONDAY, is_free=never_free, start=MONDAY)

    assert debt == NO_DEBT
    assert debt.surcharge_on(MONDAY) == 0


def test_a_charged_day_is_not_owed(hmac_key: Path):
    """Days with a charge drop out of the missed count and the amount owed."""
    ledger = Ledger()
    add_charge(ledger, MONDAY, key_file=hmac_key)
    add_charge(ledger, SATURDAY, key_file=hmac_key)

    debt = compute_debt(ledger, day=NEXT_MONDAY, is_free=never_free, start=MONDAY)

    assert debt.missed_days == 5
    assert debt.owed == 4 + 2


def test_a_free_day_is_not_owed_and_is_only_looked_up_when_uncharged(hmac_key: Path):
    """Free days are not owed, and charged days never query the pool."""
    ledger = Ledger()
    add_charge(ledger, MONDAY, key_file=hmac_key)
    asked: list[date] = []

    def pool(day: date) -> bool:
        asked.append(day)
        return day in {SATURDAY, SUNDAY}

    debt = compute_debt(ledger, day=NEXT_MONDAY, is_free=pool, start=MONDAY)

    assert debt.missed_days == 4
    assert debt.owed == 4
    assert MONDAY not in asked, "the pool is consulted only for uncharged days"


@pytest.mark.usefixtures("hmac_key")
def test_the_window_starts_at_the_epoch_not_before():
    """Days before the start date are never owed."""
    debt = compute_debt(Ledger(), day=NEXT_MONDAY, is_free=never_free, start=SATURDAY)

    assert debt.missed_days == 2
    assert debt.owed == 4


def test_the_default_epoch_is_the_constant(debt_starts):
    """Without an explicit start, the debt window opens at the configured epoch."""
    debt_starts(WEDNESDAY)

    debt = compute_debt(Ledger(), day=NEXT_MONDAY, is_free=never_free)

    assert debt.missed_days == 5


def test_a_surcharged_charge_repays_one(hmac_key: Path):
    """A signed charge with a surcharge of 1 repays one owed credit."""
    ledger = Ledger()
    append(ledger, [charge_entry(TUESDAY, now=NOW, key_file=hmac_key, surcharge=1)])

    debt = compute_debt(ledger, day=WEDNESDAY, is_free=never_free, start=MONDAY)

    assert debt.owed == 1  # Monday
    assert debt.repaid == 1
    assert debt.outstanding == 0
    assert debt.surcharge_on(MONDAY) == 0


def test_overpayment_never_becomes_credit():
    """Repaying more than owed leaves zero outstanding, never negative."""
    assert Debt(owed=1, repaid=5, missed_days=1).outstanding == 0


def test_deleting_the_ledger_grows_the_debt(hmac_key: Path):
    """The property that makes storing debt unnecessary: an empty ledger owes
    the whole window."""
    full = Ledger()
    for offset in range(7):
        add_charge(full, MONDAY + timedelta(days=offset), key_file=hmac_key)

    before = compute_debt(full, day=NEXT_MONDAY, is_free=never_free, start=MONDAY)
    after = compute_debt(Ledger(), day=NEXT_MONDAY, is_free=never_free, start=MONDAY)

    assert before.outstanding == 0
    assert after.outstanding == 9


def test_cost_phrase_spells_out_the_surcharge():
    """The cost phrase shows the base price and the debt surcharge."""
    owing = Debt(owed=3, repaid=0, missed_days=2)

    assert cost_phrase(MONDAY, 1, NO_DEBT) == "Monday costs 1"
    assert cost_phrase(MONDAY, 2, owing) == "Monday costs 2 (1 +1 debt)"
    assert cost_phrase(SATURDAY, 3, owing) == "Saturday costs 3 (2 +1 debt)"


def test_debt_line_reads_as_a_sentence():
    """The debt line and summary render as readable sentences."""
    assert debt_line(NO_DEBT) == "No debt -- on track"
    assert debt_line(Debt(owed=2, repaid=0, missed_days=1)) == (
        "Debt: 2 credits outstanding (1 missed day owed 2, 0 repaid) "
        "-- +1 on Mon/Fri/Sat/Sun until repaid"
    )
    assert debt_summary(Debt(owed=4, repaid=1, missed_days=3)) == (
        "3 credits outstanding (3 missed days owed 4, 1 repaid)"
    )
