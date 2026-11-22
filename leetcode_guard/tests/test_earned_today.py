"""Credits earned today, for the study strip's filled dots (display only).

Every source counts in the unit ``owed`` is counted in: theory minutes, a
finished module, accepted solves (difficulty-weighted).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
import logging
from typing import TYPE_CHECKING

from leetcode_guard._difficulty import WeightTable, load_weights
from leetcode_guard._earned_today import strip_counts
from leetcode_guard._gate import decide
from leetcode_guard._gate_progress import earned_today, progress_counts
from leetcode_guard._ledger_entries import charge_entry, credit_entry
from leetcode_guard._ledger_io import Ledger, append
from leetcode_guard._theory_credit import theory_entry
from leetcode_guard._theory_finish import finish_entry
from leetcode_guard._theory_pool import Tier
from leetcode_guard.tests._ledger_fixtures import (
    FRIDAY,
    MONDAY,
    NOW,
    forged_credit,
    submission,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from leetcode_guard._ledger import LedgerEntry

STAMP = (MONDAY, NOW)
# Current-era prices (Mon/Fri 3); the fixture week is in the older 1-credit era.
PRICED_MONDAY = date(2026, 11, 23)
PRICED_FRIDAY = date(2026, 11, 20)


def solve(key: Path, ident: str, slug: str = "two-sum", *, day=MONDAY) -> LedgerEntry:
    """One signed accepted-submission credit."""
    return credit_entry(submission(ident, slug), day=day, now=NOW, key_file=key)


def ledger_of(*entries: LedgerEntry) -> Ledger:
    """A ledger holding exactly these entries."""
    ledger = Ledger()
    append(ledger, list(entries))
    return ledger


def test_an_empty_ledger_earned_nothing():
    """Nothing recorded is zero, a count and not an unknown."""
    assert earned_today(Ledger(), day=MONDAY, weights=None) == 0


def test_every_source_counts_once_each(hmac_key: Path):
    """A solve, a theory-minute credit and a finished module are one apiece."""
    ledger = ledger_of(
        solve(hmac_key, "s1"),
        theory_entry(STAMP, Tier("u", 12), n=1, key_file=hmac_key),
        finish_entry(STAMP, unit="u", subject="s", module="m", key_file=hmac_key),
    )

    assert earned_today(ledger, day=MONDAY, weights=None) == 3


def test_a_weighted_solve_fills_its_weight(hmac_key: Path):
    """A Medium solve is worth two, the unit ``owed`` is counted in."""
    ledger = ledger_of(solve(hmac_key, "s1", "med"), solve(hmac_key, "s2", "easy"))
    weights = WeightTable(levels={"med": "Medium", "easy": "Easy"})

    assert earned_today(ledger, day=MONDAY, weights=weights) == 3


def test_another_days_credits_do_not_count(hmac_key: Path):
    """Yesterday's credit and a theory credit dated Friday stay out."""
    ledger = ledger_of(
        solve(hmac_key, "old", day=FRIDAY),
        solve(hmac_key, "now"),
        theory_entry((FRIDAY, NOW), Tier("u", 12), n=1, key_file=hmac_key),
    )

    assert earned_today(ledger, day=MONDAY, weights=None) == 1


def test_a_charge_is_not_an_earning(hmac_key: Path):
    """Spending today's price is not earning it."""
    ledger = ledger_of(
        solve(hmac_key, "s1"), charge_entry(MONDAY, now=NOW, key_file=hmac_key)
    )

    assert earned_today(ledger, day=MONDAY, weights=None) == 1


def test_an_unverified_credit_is_not_drawn(hmac_key: Path):
    """The credit rule: a forged row never fills a dot."""
    ledger = ledger_of(solve(hmac_key, "s1"), forged_credit(day=MONDAY))

    assert earned_today(ledger, day=MONDAY, weights=None) == 1


def test_a_bad_signature_is_not_drawn(hmac_key: Path):
    """A signed row whose body was edited afterwards does not count."""
    good = solve(hmac_key, "s1")
    edited = replace(good, entry_id="ac:s2", verified=False)

    assert earned_today(ledger_of(good, edited), day=MONDAY, weights=None) == 1


def banked_decision(ledger: Ledger, key: Path):
    """The gate's verdict for a Monday over ``ledger``."""
    return decide(ledger, day=PRICED_MONDAY, now=NOW, key_file=key)


def test_the_strip_counts_are_hollow_owed_then_filled_done(hmac_key: Path):
    """One pure function feeds the dots: 2 banked on Friday, none today, 1 owed."""
    ledger = ledger_of(
        solve(hmac_key, "b1", day=PRICED_FRIDAY),
        solve(hmac_key, "b2", day=PRICED_FRIDAY),
    )

    assert strip_counts(
        ledger, banked_decision(ledger, hmac_key), key_file=hmac_key
    ) == (
        1,
        2,
    )


def test_the_strip_and_the_signed_row_never_disagree(hmac_key: Path):
    """Same inputs, same numbers: filled is done, hollow is target minus done."""
    ledger = ledger_of(solve(hmac_key, "s1", day=PRICED_MONDAY))
    decision = banked_decision(ledger, hmac_key)
    done, target = progress_counts(
        ledger, decision, weights=load_weights(key_file=hmac_key)
    )

    assert strip_counts(ledger, decision, key_file=hmac_key) == (target - done, done)


def test_a_failed_strip_read_still_draws_what_is_owed(
    hmac_key: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """Cannot read: hollow dots for the owed credits, no invented filled dot."""
    ledger = ledger_of(solve(hmac_key, "s1", day=PRICED_MONDAY))

    def broken(**_kwargs: object) -> WeightTable:
        message = "difficulty file unreadable"
        raise OSError(message)

    monkeypatch.setattr("leetcode_guard._earned_today.load_weights", broken)

    with caplog.at_level(logging.WARNING):
        got = strip_counts(ledger, banked_decision(ledger, hmac_key), key_file=hmac_key)

    assert got == (2, None)
    assert any(r.levelno >= logging.WARNING for r in caplog.records)
