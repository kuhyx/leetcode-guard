"""Tests for how surcharged charges repay the missed-day debt, and the gate's use of it."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _gate_today
from leetcode_guard._debt import NO_DEBT, compute_debt
from leetcode_guard._ledger import LedgerEntry
from leetcode_guard._ledger_entries import charge_entry
from leetcode_guard._ledger_io import Ledger, append, load_ledger, save_ledger
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    NOW,
    TUESDAY,
    WEDNESDAY,
    ledger_with_credits,
)
from leetcode_guard.tests.test_debt import never_free

if TYPE_CHECKING:
    from pathlib import Path


def test_a_forged_surcharge_counts_as_spent_but_repays_nothing(
    tmp_path: Path, hmac_key: Path
):
    """The bypass this rule exists for: append an unsigned charge with a huge
    amount and call the debt paid. The amount is spent -- discarding it would
    be a refund -- and the debt is untouched."""
    path = tmp_path / "ledger.json"
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    append(
        ledger,
        [
            LedgerEntry(
                entry_id=f"charge:{TUESDAY.isoformat()}",
                kind="charge",
                day=TUESDAY.isoformat(),
                created_at=NOW.isoformat(),
                amount=50,
                signature=None,
            )
        ],
    )
    save_ledger(path, ledger)
    reloaded = load_ledger(path, key_file=hmac_key)

    debt = compute_debt(reloaded, day=WEDNESDAY, is_free=never_free, start=MONDAY)

    assert debt.repaid == 0
    assert debt.owed == 1


def test_with_an_unreadable_key_this_devices_surcharge_still_repays(
    tmp_path: Path, hmac_key: Path, missing_key: Path
):
    """A charge signed here still repays when the key cannot be read later."""
    path = tmp_path / "ledger.json"
    ledger = Ledger()
    append(ledger, [charge_entry(TUESDAY, now=NOW, key_file=hmac_key, surcharge=1)])
    save_ledger(path, ledger)

    debt = compute_debt(
        load_ledger(path, key_file=missing_key),
        day=WEDNESDAY,
        is_free=never_free,
        start=MONDAY,
    )

    assert debt.repaid == 1


@pytest.mark.usefixtures("hmac_key")
def test_a_charge_with_an_unparsable_day_repays_nothing():
    """A charge whose day is not a date repays nothing."""
    ledger = Ledger()
    append(
        ledger,
        [
            LedgerEntry(
                entry_id="charge:garbage",
                kind="charge",
                day="not-a-date",
                created_at=NOW.isoformat(),
                amount=9,
                verified=True,
            )
        ],
    )

    debt = compute_debt(ledger, day=TUESDAY, is_free=never_free, start=MONDAY)

    assert debt.repaid == 0


def test_a_surcharge_paid_before_the_epoch_does_not_count(hmac_key: Path):
    """Moving the epoch forward forgives both sides: the days before it are
    not owed, and a surcharge paid before it repays nothing after it."""
    ledger = Ledger()
    append(ledger, [charge_entry(MONDAY, now=NOW, key_file=hmac_key, surcharge=1)])

    debt = compute_debt(ledger, day=WEDNESDAY, is_free=never_free, start=TUESDAY)

    assert debt.owed == 1
    assert debt.repaid == 0


@pytest.mark.usefixtures("hmac_key")
def test_decide_today_computes_the_debt_for_real_runs(debt_starts):
    """A real gate run derives the debt and keeps the Wednesday price at 1."""
    debt_starts(MONDAY)

    decision = _gate_today.decide_today(Ledger(), day=WEDNESDAY, now=NOW)

    assert decision.debt.missed_days == 2
    assert decision.cost == 1  # Wednesday: debt never surcharges Tue-Thu


@pytest.mark.usefixtures("hmac_key")
def test_the_demo_shows_no_debt(debt_starts):
    """The demo deletes its ledger every run, so a derived debt there would be
    every day since the epoch and the surface would lie."""
    debt_starts(MONDAY)

    decision = _gate_today.decide_today(Ledger(), day=WEDNESDAY, now=NOW, demo=True)

    assert decision.debt == NO_DEBT
    assert decision.cost == 1
