"""The signed progress row: done N of target M for today, and what it never does.

kuhy decided (2026-11-22) that every gate pays its shutdown bonus in proportion
to progress. ``earned_time`` cannot know this guard's price, so the guard signs
the fact. The row is inert here: nothing this module's rows touch may decide,
charge, credit or lock. Each safety test is named after the rule it pins.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import earned_time
import pytest

from leetcode_guard._difficulty import WeightTable
from leetcode_guard._gate_progress import (
    apply_progress,
    earned_today,
    progress_counts,
)
from leetcode_guard._ledger import to_json
from leetcode_guard._ledger_entries import progress_entry
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard.tests._ledger_fixtures import (
    ledger_with_credits,
)
from leetcode_guard.tests._progress_fixtures import (
    FRIDAY,
    MONDAY,
    NOW,
    TUESDAY,
    decision_of,
    shaped,
    sign_progress,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("earned", "available", "needed", "expected"),
    [
        (5, 3, 2, (5, 7)),
        (0, 2, 1, (2, 3)),
        (1, 2, 1, (2, 3)),
        (1, -2, 5, (1, 6)),
        (0, -2, 3, (0, 3)),
        (0, 0, 3, (0, 3)),
    ],
)
def test_the_numbers_follow_kuhys_answers(
    hmac_key: Path, earned: int, available: int, needed: int, expected: tuple
):
    """done = max(earned today, available, 0); target = done + needed."""
    ledger, decision = shaped(
        earned=earned, available=available, needed=needed, key=hmac_key
    )

    assert progress_counts(ledger, decision, weights=None) == expected


def test_today_earned_prices_solves_by_weight_and_theory_at_one(hmac_key: Path):
    """The existing weighted pricing, now owned by the decider side."""
    ledger = ledger_with_credits(2, day=MONDAY, key_file=hmac_key)
    weights = WeightTable(levels={"two-sum": "Hard"})

    assert earned_today(ledger, day=MONDAY, weights=weights) == 8
    assert earned_today(ledger, day=TUESDAY, weights=weights) == 0


def test_one_credit_today_writes_done_one_of_the_price(hmac_key: Path):
    """The row id, contract keys and signature, on a real decision."""
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    decision = decision_of(ledger, hmac_key)
    path = hmac_key.parent / "ledger.json"

    assert apply_progress(ledger, decision, path, now=NOW, key_file=hmac_key)

    row = ledger.entries["progress:2026-11-23:1:3"]
    assert (row.kind, row.day, row.amount) == ("progress", "2026-11-23", 0)
    assert row.detail == {
        "source": "leetcode",
        "for_day": "2026-11-23",
        "done": "1",
        "target": "3",
    }
    assert row.device
    assert row.created_at == NOW.isoformat()
    assert load_ledger(path, key_file=hmac_key).entries[row.entry_id].verified


def test_banked_credit_counts_as_done_ahead(hmac_key: Path):
    """Two credits banked on Friday, none today, one still needed: 2 of 3."""
    ledger = ledger_with_credits(2, day=FRIDAY, key_file=hmac_key)
    decision = decision_of(ledger, hmac_key)

    assert decision.needed == 1
    assert progress_counts(ledger, decision, weights=None) == (2, 3)
    assert sign_progress(ledger, decision, hmac_key)
    assert ledger.has("progress:2026-11-23:2:3")


def test_the_row_verifies_under_earned_time(hmac_key: Path):
    """The reader is written against exactly this row and its signature."""
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    sign_progress(ledger, decision_of(ledger, hmac_key), hmac_key)

    row = to_json(ledger.entries["progress:2026-11-23:1:3"])

    assert earned_time.verified(row, hmac_key.read_bytes().strip())


def test_an_edited_row_fails_earned_time_verification(hmac_key: Path):
    """Raising ``done`` after signing buys nothing."""
    entry = progress_entry(for_day=MONDAY, done=1, target=3, now=NOW, key_file=hmac_key)
    row = to_json(entry)
    row["detail"] = {**row["detail"], "done": "3"}

    assert earned_time.verified(to_json(entry), hmac_key.read_bytes().strip())
    assert not earned_time.verified(row, hmac_key.read_bytes().strip())


def test_an_edited_row_is_not_verified_on_load(hmac_key: Path):
    """The guard's own load flags it too (a tampered count, never counted)."""
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    path = hmac_key.parent / "ledger.json"
    apply_progress(
        ledger, decision_of(ledger, hmac_key), path, now=NOW, key_file=hmac_key
    )
    path.write_text(path.read_text().replace('"done": "1"', '"done": "3"'))

    reloaded = load_ledger(path, key_file=hmac_key)

    assert reloaded.entries["progress:2026-11-23:1:3"].verified is False
    assert reloaded.tampered == 1
