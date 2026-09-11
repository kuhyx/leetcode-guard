"""Tests for the missed-day debt: derived from calendar and ledger, never stored."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from leetcode_guard import _gate_today
from leetcode_guard._debt import (
    NO_DEBT,
    Debt,
    compute_debt,
    cost_phrase,
    debt_line,
    debt_summary,
)
from leetcode_guard._ledger import LedgerEntry
from leetcode_guard._ledger_entries import charge_entry
from leetcode_guard._ledger_io import Ledger, append, load_ledger, save_ledger
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    NOW,
    SATURDAY,
    SUNDAY,
    TUESDAY,
    WEDNESDAY,
    add_charge,
    ledger_with_credits,
)

if TYPE_CHECKING:
    from pathlib import Path

NEXT_MONDAY = MONDAY + timedelta(days=7)


def never_free(_day: date) -> bool:
    return False


def test_every_uncharged_day_in_the_window_is_owed_at_its_price(hmac_key: Path):
    """Monday to Sunday with nothing charged: five weekdays and a weekend."""
    debt = compute_debt(Ledger(), day=NEXT_MONDAY, is_free=never_free, start=MONDAY)

    assert debt.missed_days == 7
    assert debt.owed == 5 + 2 + 2
    assert debt.repaid == 0
    assert debt.outstanding == 9
    assert debt.surcharge == 1


def test_today_is_not_owed_while_it_is_still_today():
    debt = compute_debt(Ledger(), day=MONDAY, is_free=never_free, start=MONDAY)

    assert debt == NO_DEBT
    assert debt.surcharge == 0


def test_a_charged_day_is_not_owed(hmac_key: Path):
    ledger = Ledger()
    add_charge(ledger, MONDAY, key_file=hmac_key)
    add_charge(ledger, SATURDAY, key_file=hmac_key)

    debt = compute_debt(ledger, day=NEXT_MONDAY, is_free=never_free, start=MONDAY)

    assert debt.missed_days == 5
    assert debt.owed == 4 + 2


def test_a_free_day_is_not_owed_and_is_only_looked_up_when_uncharged(hmac_key: Path):
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


def test_the_window_starts_at_the_epoch_not_before(hmac_key: Path):
    debt = compute_debt(Ledger(), day=NEXT_MONDAY, is_free=never_free, start=SATURDAY)

    assert debt.missed_days == 2
    assert debt.owed == 4


def test_the_default_epoch_is_the_constant(debt_starts):
    debt_starts(WEDNESDAY)

    debt = compute_debt(Ledger(), day=NEXT_MONDAY, is_free=never_free)

    assert debt.missed_days == 5


def test_a_surcharged_charge_repays_one(hmac_key: Path):
    ledger = Ledger()
    append(ledger, [charge_entry(TUESDAY, now=NOW, key_file=hmac_key, surcharge=1)])

    debt = compute_debt(ledger, day=WEDNESDAY, is_free=never_free, start=MONDAY)

    assert debt.owed == 1  # Monday
    assert debt.repaid == 1
    assert debt.outstanding == 0
    assert debt.surcharge == 0


def test_overpayment_never_becomes_credit():
    assert Debt(owed=1, repaid=5, missed_days=1).outstanding == 0


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


def test_a_charge_with_an_unparsable_day_repays_nothing(hmac_key: Path):
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
    owing = Debt(owed=3, repaid=0, missed_days=2)

    assert cost_phrase(TUESDAY, 1, NO_DEBT) == "Tuesday costs 1"
    assert cost_phrase(TUESDAY, 2, owing) == "Tuesday costs 2 (1 +1 debt)"


def test_debt_line_reads_as_a_sentence():
    assert debt_line(NO_DEBT) == "No debt -- on track"
    assert debt_line(Debt(owed=2, repaid=0, missed_days=1)) == (
        "Debt: 2 credits outstanding (1 missed day owed 2, 0 repaid) "
        "-- +1 per day until repaid"
    )
    assert debt_summary(Debt(owed=4, repaid=1, missed_days=3)) == (
        "3 credits outstanding (3 missed days owed 4, 1 repaid)"
    )


def test_a_surcharge_paid_before_the_epoch_does_not_count(hmac_key: Path):
    """Moving the epoch forward forgives both sides: the days before it are
    not owed, and a surcharge paid before it repays nothing after it."""
    ledger = Ledger()
    append(ledger, [charge_entry(MONDAY, now=NOW, key_file=hmac_key, surcharge=1)])

    debt = compute_debt(ledger, day=WEDNESDAY, is_free=never_free, start=TUESDAY)

    assert debt.owed == 1
    assert debt.repaid == 0


def test_decide_today_computes_the_debt_for_real_runs(hmac_key: Path, debt_starts):
    debt_starts(MONDAY)

    decision = _gate_today.decide_today(Ledger(), day=WEDNESDAY, now=NOW)

    assert decision.debt.missed_days == 2
    assert decision.cost == 2


def test_the_demo_shows_no_debt(hmac_key: Path, debt_starts):
    """The demo deletes its ledger every run, so a derived debt there would be
    every day since the epoch and the surface would lie."""
    debt_starts(MONDAY)

    decision = _gate_today.decide_today(Ledger(), day=WEDNESDAY, now=NOW, demo=True)

    assert decision.debt == NO_DEBT
    assert decision.cost == 1
