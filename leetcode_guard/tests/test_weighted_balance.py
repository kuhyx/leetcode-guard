"""Credits are difficulty-weighted at read time; the signed rows never change."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _constants
from leetcode_guard._balance import compute_balance
from leetcode_guard._daycost import day_cost
from leetcode_guard._difficulty import WeightTable, difficulty_row
from leetcode_guard._gate import GateState
from leetcode_guard._gate_today import decide_today
from leetcode_guard._ledger import CREDIT, LedgerEntry, sign
from leetcode_guard._ledger_entries import credit_entry, seen_entry
from leetcode_guard._ledger_io import Ledger, append, save_ledger
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    NOW,
    SATURDAY,
    forged_credit,
    submission,
)

if TYPE_CHECKING:
    from pathlib import Path

LEVELS = {"easy-p": "Easy", "medium-p": "Medium", "hard-p": "Hard"}


def solved(ledger: Ledger, key: Path, *slugs: str) -> None:
    """Append one signed Monday credit per slug to the ledger."""
    append(
        ledger,
        [
            credit_entry(
                submission(f"id-{index}-{slug}", slug),
                day=MONDAY,
                now=NOW,
                key_file=key,
            )
            for index, slug in enumerate(slugs)
        ],
    )


def test_easy_medium_hard_are_worth_one_two_four(hmac_key: Path):
    """Easy, Medium and Hard solves weigh one, two and four credits."""
    ledger = Ledger()
    solved(ledger, hmac_key, "easy-p", "medium-p", "hard-p", "medium-p")

    balance = compute_balance(ledger, WeightTable(levels=dict(LEVELS)))

    assert balance.credits == 1 + 2 + 4 + 2
    assert balance.solves == {"Easy": 1, "Medium": 2, "Hard": 1, "unknown": 0}


def test_without_a_table_every_credit_is_flat_one(hmac_key: Path):
    """With no weight table every credit counts as one."""
    ledger = Ledger()
    solved(ledger, hmac_key, "medium-p", "hard-p")

    assert compute_balance(ledger).credits == 2


def test_unknown_difficulty_counts_as_easy_with_one_warning(
    hmac_key: Path, caplog: pytest.LogCaptureFixture
):
    """An unknown difficulty weighs one credit and logs a single warning."""
    ledger = Ledger()
    solved(ledger, hmac_key, "a", "b", "c")
    table = WeightTable(levels={"a": "Hard"})

    with caplog.at_level(logging.WARNING):
        balance = compute_balance(ledger, table)

    assert balance.credits == 4 + 1 + 1
    assert balance.solves["unknown"] == 2
    messages = [
        r.getMessage() for r in caplog.records if "difficulty" in r.getMessage()
    ]
    assert len(messages) == 1
    assert "2 solved" in messages[0]


def test_seen_markers_stay_worth_nothing(hmac_key: Path):
    """Seen markers earn no credit even on a Hard problem."""
    ledger = Ledger()
    append(
        ledger,
        [
            seen_entry(
                submission("s1", "hard-p"), day=MONDAY, now=NOW, key_file=hmac_key
            )
        ],
    )

    balance = compute_balance(ledger, WeightTable(levels=dict(LEVELS)))

    assert balance.credits == 0
    assert sum(balance.solves.values()) == 0


def test_a_forged_hard_credit_is_discounted_not_weighted(hmac_key: Path):
    """A forged credit is discounted instead of weighted."""
    ledger = Ledger()
    solved(ledger, hmac_key, "hard-p")
    forged = forged_credit()
    append(ledger, [forged])
    ledger.entries[forged.entry_id] = forged

    balance = compute_balance(ledger, WeightTable(levels=dict(LEVELS)))

    assert balance.credits == 4
    assert balance.discounted >= 1


def test_a_credit_without_a_slug_keeps_its_own_amount(hmac_key: Path):
    """A legacy credit with no slug keeps its stored amount."""
    ledger = Ledger()
    append(
        ledger,
        [
            sign(
                LedgerEntry(
                    entry_id="ac:legacy",
                    kind=CREDIT,
                    day=MONDAY.isoformat(),
                    created_at=NOW.isoformat(),
                    amount=3,
                ),
                key_file=hmac_key,
            )
        ],
    )

    balance = compute_balance(ledger, WeightTable(levels=dict(LEVELS)))

    assert balance.credits == 3
    assert balance.solves["unknown"] == 0


def test_the_stored_amount_is_never_rewritten(hmac_key: Path):
    """A Hard credit is still stored as amount one; weighting happens at read time."""
    entry = credit_entry(
        submission("1", "hard-p"), day=MONDAY, now=NOW, key_file=hmac_key
    )

    assert entry.amount == 1


@pytest.mark.usefixtures("data_dir")
def test_decide_today_prices_credits_from_the_signed_cache(hmac_key: Path):
    """A Medium solve covers a 2-credit day; priced flat it would not."""
    day = SATURDAY
    ledger = Ledger()
    solved(ledger, hmac_key, "medium-p")
    assert day_cost(day) == 2
    rows = Ledger()
    append(
        rows,
        [difficulty_row("medium-p", "Medium", now=NOW, key_file=hmac_key)],
    )
    save_ledger(_constants.DIFFICULTY_FILE, rows)

    decision = decide_today(ledger, day=day, now=NOW, key_file=hmac_key)

    assert decision.balance.credits == 2
    assert decision.state is GateState.UNLOCKED_CHARGED_NOW
