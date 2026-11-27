"""A cleared review pays 1 credit (kuhy 2026-11-27, part 9005c9b4-1).

``review-clear:<day>:<unit>`` is minted once per unit per day when that day
has signed tutor review rows on the unit's modules and the signed
``review_due.json`` shows 0 cards due for every module of the unit. The
scenario is ``_theory_scenario``'s: module ``a`` done, so SOLVE(a).
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from leetcode_guard import _tutor_signed
from leetcode_guard._ledger_io import Ledger, load_ledger
from leetcode_guard._phase import NONE_STATE, PhaseState
from leetcode_guard._review_clear import clear_id, due_review_clear
from leetcode_guard._theory_credit import theory_credits
from leetcode_guard.tests._review_fixtures import DAY, NOW, poll, put, reviews
from leetcode_guard.tests._theory_scenario import began, states, world
from leetcode_guard.tests._tutor_fixtures import ALGO, due_row, write_due

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

NOW_MS = int(NOW.timestamp() * 1000)
WRITTEN = (NOW - timedelta(minutes=1)).timestamp()
"""The due row's ``at``: written just after the review, today."""
LATER = [NOW_MS + 3_600_000, NOW_MS + 86_400_000]


SOLVE_A = PhaseState(unit="a", phase="solve", subject=ALGO, modules=("a",))


def _solve_a(tmp_path, monkeypatch, key: Path) -> None:
    world(tmp_path, monkeypatch)
    states(key, "a")
    began(key, phase="solve")


def _clears(ledger: Ledger) -> list[str]:
    return sorted(
        e.entry_id for e in ledger.entries.values() if "review-clear" in e.entry_id
    )


def test_clearing_every_due_card_of_the_unit_mints_one_credit(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """Reviews today on ``a`` and no card of ``a`` due now: one credit, saved."""
    _solve_a(tmp_path, monkeypatch, hmac_key)
    put(reviews(hmac_key, "a", 2))
    write_due([due_row("a", LATER, at=WRITTEN, key_file=hmac_key)])
    ledger = Ledger()

    poll(ledger, data_dir, hmac_key)

    assert _clears(ledger) == [f"review-clear:{DAY.isoformat()}:a"]
    row = ledger.entries[clear_id(DAY, "a")]
    assert (row.kind, row.amount, row.day) == ("credit", 1, DAY.isoformat())
    assert row.detail["source"] == "tutor-theory"
    assert row.detail["unit"] == "a"
    assert row.detail["cards"] == "2"
    assert "repair" not in row.detail
    assert theory_credits(ledger, day=DAY) == (1, 1)
    saved = load_ledger(data_dir / "ledger.json", key_file=hmac_key)
    assert saved.has(clear_id(DAY, "a"))


def test_it_pays_once_per_unit_per_day(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """A second clear the same day mints nothing."""
    _solve_a(tmp_path, monkeypatch, hmac_key)
    put(reviews(hmac_key, "a", 2))
    write_due([due_row("a", LATER, at=WRITTEN, key_file=hmac_key)])
    ledger = Ledger()
    poll(ledger, data_dir, hmac_key)

    assert poll(ledger, data_dir, hmac_key).minted == ()
    assert len(_clears(ledger)) == 1


def test_a_card_still_due_pays_nothing(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """One card due at the poll's moment: not cleared."""
    _solve_a(tmp_path, monkeypatch, hmac_key)
    put(reviews(hmac_key, "a", 2))
    write_due([due_row("a", [NOW_MS, *LATER], at=WRITTEN, key_file=hmac_key)])
    ledger = Ledger()

    poll(ledger, data_dir, hmac_key)

    assert _clears(ledger) == []


def test_no_review_of_the_unit_today_pays_nothing(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """Reviews on another unit's card (``b1``) are not a clear of ``a``."""
    _solve_a(tmp_path, monkeypatch, hmac_key)
    put(reviews(hmac_key, "b1", 2))
    write_due([due_row("a", LATER, at=WRITTEN, key_file=hmac_key)])
    ledger = Ledger()

    poll(ledger, data_dir, hmac_key)

    assert _clears(ledger) == []


def test_a_due_row_written_on_another_day_pays_nothing(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """An older signed file put back cannot be today's clear."""
    _solve_a(tmp_path, monkeypatch, hmac_key)
    put(reviews(hmac_key, "a", 2))
    yesterday = (NOW - timedelta(days=1)).timestamp()
    write_due([due_row("a", LATER, at=yesterday, key_file=hmac_key)])
    ledger = Ledger()

    poll(ledger, data_dir, hmac_key)

    assert _clears(ledger) == []


def test_cannot_check_pays_nothing_and_says_so(
    tmp_path,
    monkeypatch,
    data_dir: Path,
    hmac_key: Path,
    caplog: pytest.LogCaptureFixture,
):
    """No ``review_due.json``: nothing minted, one warning, no raise."""
    _solve_a(tmp_path, monkeypatch, hmac_key)
    put(reviews(hmac_key, "a", 2))
    ledger = Ledger()

    with caplog.at_level(logging.WARNING):
        poll(ledger, data_dir, hmac_key)

    assert _clears(ledger) == []
    assert "review clear cannot be checked" in caplog.text


def test_a_module_without_a_due_row_is_cannot_check(
    tmp_path,
    monkeypatch,
    data_dir: Path,
    hmac_key: Path,
    caplog: pytest.LogCaptureFixture,
):
    """A deleted row cannot be told from never written: nothing minted."""
    _solve_a(tmp_path, monkeypatch, hmac_key)
    put(reviews(hmac_key, "a", 2))
    write_due([due_row("b1", LATER, at=WRITTEN, key_file=hmac_key)])
    ledger = Ledger()

    with caplog.at_level(logging.WARNING):
        poll(ledger, data_dir, hmac_key)

    assert _clears(ledger) == []
    assert "no due row" in caplog.text


def test_an_unreadable_tutor_ledger_pays_nothing(tmp_path, monkeypatch, hmac_key: Path):
    """No C1 rows to prove a review happened: nothing."""
    _solve_a(tmp_path, monkeypatch, hmac_key)
    write_due([due_row("a", LATER, at=WRITTEN, key_file=hmac_key)])
    (_tutor_signed.TUTOR_DIR / "ledger.json").unlink(missing_ok=True)

    assert (
        due_review_clear(Ledger(), SOLVE_A, stamp=(DAY, NOW), key_file=hmac_key) == []
    )


def test_no_current_unit_pays_nothing(hmac_key: Path):
    """``none``: every unit finished, nothing to clear."""
    assert (
        due_review_clear(Ledger(), NONE_STATE, stamp=(DAY, NOW), key_file=hmac_key)
        == []
    )
