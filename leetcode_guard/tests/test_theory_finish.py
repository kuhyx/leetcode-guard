"""The finish credit: a module signed done today pays +1, once per module, ever."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._ledger_io import Ledger, load_ledger
from leetcode_guard._theory_credit import theory_credits
from leetcode_guard.tests._finish_fixtures import (
    A_ID,
    B1_ID,
    DAY,
    NOW,
    TODAY,
    YESTERDAY,
    flips,
    ids,
    poll,
    solved_a1,
)
from leetcode_guard.tests._theory_scenario import began, taught, world
from leetcode_guard.tests._tutor_fixtures import ALGO

if TYPE_CHECKING:
    from pathlib import Path


def test_a_module_finished_under_12_minutes_pays_one_credit(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """9 minutes pay nothing alone; the finish pays 1, shaped as a signed credit."""
    world(tmp_path, monkeypatch)
    began(hmac_key)
    flips(hmac_key, ("a", True, TODAY))
    taught(hmac_key, NOW, ("a", 9))
    ledger = Ledger()

    result = poll(ledger, data_dir, hmac_key)

    assert (result.minutes, ids(result)) == (9, [A_ID])
    entry = result.minted[0]
    assert (entry.kind, entry.amount, entry.day) == ("credit", 1, str(DAY))
    assert entry.detail == {
        "source": "tutor-theory",
        "unit": "a",
        "subject": ALGO,
        "module": "a",
        "finish": "1",
    }
    saved = load_ledger(data_dir / "ledger.json", key_file=hmac_key)
    assert set(saved.entries) == {A_ID}
    assert saved.entries[A_ID].verified
    assert theory_credits(ledger, day=DAY) == (1, 1)
    assert poll(ledger, data_dir, hmac_key).minted == ()


def test_24_minutes_and_the_finish_pay_three(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """Minute credits 1 and 2, then the finish: three, the finish keeps its own id."""
    world(tmp_path, monkeypatch)
    began(hmac_key)
    flips(hmac_key, ("a", True, TODAY))
    taught(hmac_key, NOW, ("a", 24))

    result = poll(Ledger(), data_dir, hmac_key)

    assert ids(result) == [f"theory:{DAY}:1", f"theory:{DAY}:2", A_ID]


def test_one_module_of_two_pays_while_the_unit_is_still_in_theory(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """THEORY(b) with b1 done and b2 not: b1 pays, once per module."""
    world(tmp_path, monkeypatch)
    ledger = Ledger()
    solved_a1(ledger, hmac_key)
    flips(hmac_key, ("a", True, YESTERDAY), ("b1", True, TODAY), ("b2", False, TODAY))
    taught(hmac_key, NOW)

    result = poll(ledger, data_dir, hmac_key)

    assert result.state is not None
    assert (result.state.unit, result.state.phase) == ("b", "theory")
    assert ids(result) == [B1_ID]
    flips(hmac_key, ("a", True, YESTERDAY), ("b1", True, TODAY), ("b2", True, TODAY))
    assert ids(poll(ledger, data_dir, hmac_key)) == [f"theory-done:{ALGO}:b2"]


def test_a_module_that_flips_back_and_is_done_again_pays_once(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """done, not done (a card was added), done again: still the one credit."""
    world(tmp_path, monkeypatch)
    taught(hmac_key, NOW)
    flips(hmac_key, ("a", True, TODAY))
    ledger = Ledger()
    assert ids(poll(ledger, data_dir, hmac_key)) == [A_ID]

    flips(hmac_key, ("a", True, TODAY), ("a", False, TODAY + 1))
    assert poll(ledger, data_dir, hmac_key).minted == ()
    flips(hmac_key, ("a", True, TODAY), ("a", False, TODAY + 1), ("a", True, TODAY + 2))
    assert poll(ledger, data_dir, hmac_key).minted == ()
    assert set(ledger.entries) == {A_ID}


def test_a_done_row_dated_yesterday_pays_nothing_and_a_deleted_ledger_remints_todays(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """No back-pay: a's done day was yesterday; b1's is today, and only it re-mints."""
    world(tmp_path, monkeypatch)
    taught(hmac_key, NOW)
    flips(hmac_key, ("a", True, YESTERDAY))
    assert poll(Ledger(), data_dir, hmac_key).minted == ()

    first = Ledger()
    solved_a1(first, hmac_key)
    flips(hmac_key, ("a", True, YESTERDAY), ("b1", True, TODAY))
    assert ids(poll(first, data_dir, hmac_key)) == [B1_ID]
    again = Ledger()
    solved_a1(again, hmac_key)
    assert ids(poll(again, data_dir, hmac_key)) == [B1_ID]
