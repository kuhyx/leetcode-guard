"""Review minutes, one rule at a time: the readers, the pool, and what the lock shows."""

from __future__ import annotations

from dataclasses import replace
import json
from typing import TYPE_CHECKING

from leetcode_guard import _curriculum, _theory_credit, _tutor_signed
from leetcode_guard._ledger_io import Ledger, append
from leetcode_guard._phase import PhaseState
from leetcode_guard._theory_pool import (
    Tier,
    paying_minutes,
    paying_pool,
    spent_elsewhere,
)
from leetcode_guard._tutor_minutes import review_minutes
from leetcode_guard._unit_view import read_unit
from leetcode_guard.tests._review_fixtures import (
    DAY,
    NOW,
    lessons,
    poll,
    put,
    reviews,
    theory_rows,
)
from leetcode_guard.tests._theory_scenario import began, states, world
from leetcode_guard.tests._tutor_fixtures import ALGO, review_row, write_tutor

if TYPE_CHECKING:
    from pathlib import Path

    from leetcode_guard._ledger import LedgerEntry


def entry(unit: str, minutes: str, spent: str | None, key: Path) -> LedgerEntry:
    """A trusted theory credit with arbitrary (string) ``minutes`` and ``reviews``."""
    row = _theory_credit.theory_entry((DAY, NOW), Tier(unit, 1), n=1, key_file=key)
    detail = {"source": "tutor-theory", "unit": unit, "minutes": minutes}
    if spent is not None:
        detail["reviews"] = spent
    return replace(row, detail=detail, verified=True)


def test_i5_the_reader_applies_each_rule_alone(hmac_key: Path):
    """``review_minutes``: mapped pair, tagged, positive int, today, smallest per id."""
    rows = [
        review_row("a-m1", 4, ended=NOW, key_file=hmac_key),
        review_row("a-m1", 3, ended=NOW, key_file=hmac_key),  # replay: smallest
        review_row("b-m1", 6, ended=NOW, key_file=hmac_key, where=(ALGO, "a")),
        review_row("c-m1", 0, ended=NOW, key_file=hmac_key),
        review_row("d-m1", 8, ended=NOW, key_file=hmac_key, where=("other", "b1")),
    ]
    odd = review_row("e-m1", 5, ended=NOW, key_file=hmac_key)
    odd_detail = odd["detail"]
    assert isinstance(odd_detail, dict)
    odd_detail["module"] = ["b1"]  # unhashable: no mapped pair, and no TypeError
    mapped = {(ALGO, "a"), (ALGO, "b1")}

    assert review_minutes([*rows, odd], mapped, day=DAY) == 3 + 6


def test_i4_rows_minted_before_the_reviews_key_existed_spent_nothing(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """A row with no ``reviews`` key reads 0 spent, so 12 reviews pay once more."""
    world(tmp_path, monkeypatch)
    states(hmac_key, "a")
    ledger = Ledger()
    append(ledger, [entry("b", "12", None, hmac_key)])
    put(reviews(hmac_key, "b1", 12))

    poll(ledger, data_dir, hmac_key)

    assert [row[0] for row in theory_rows(ledger)] == ["b", "a"]


def test_a_missing_curriculum_is_cannot_check_not_no_reviews(
    tmp_path, monkeypatch, hmac_key: Path
):
    """The mapping decides which cards count: no curriculum, no pool."""
    world(tmp_path, monkeypatch)
    put(reviews(hmac_key, "b1", 12))
    monkeypatch.setattr(_curriculum, "CURRICULUM_FILE", tmp_path / "gone.json")
    state = PhaseState(unit="a", phase="solve", subject=ALGO, modules=("a",))

    assert paying_pool(state, Ledger(), day=DAY, key_file=hmac_key) is None


def test_spent_elsewhere_reads_each_labels_highest_row_and_only_trusted_rows(
    hmac_key: Path,
):
    """Another label's spend = ``reviews`` of its top-``minutes`` row; junk reads 0."""
    rows = [
        entry("a", "12", "5", hmac_key),
        entry("a", "24", "17", hmac_key),
        entry("b", "12", None, hmac_key),
        entry("c", "x", "-3", hmac_key),
        replace(entry("d", "12", "99", hmac_key), verified=False),
        entry("mine", "12", "50", hmac_key),
    ]

    assert spent_elsewhere(rows, "mine", integrity_ok=True) == 17
    assert spent_elsewhere(rows, "a", integrity_ok=True) == 50
    assert spent_elsewhere([], "a", integrity_ok=True) == 0


def test_the_lock_and_status_show_the_same_pool_the_mint_counts(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """``read_unit`` (lock card, ``--status``, MCP, snapshot) counts lesson + reviews."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    began(hmac_key)
    put(lessons(hmac_key, "a", 3), reviews(hmac_key, "b2", 4))

    read = read_unit(data_dir / "ledger.json", day=DAY, key_file=hmac_key)

    assert read.minutes == 7
    assert read.view.theory_minutes_today == 7


def test_the_tutor_ledger_is_read_in_every_phase_since_reviews_pay_in_all(
    tmp_path, monkeypatch, hmac_key: Path
):
    """Even ``none`` (or a unit with no module) opens it: reviews pay there too."""
    world(tmp_path, monkeypatch)
    _tutor_signed.TUTOR_DIR.mkdir(parents=True, exist_ok=True)
    assert (
        paying_minutes(PhaseState("", "none"), Ledger(), day=DAY, key_file=hmac_key)
        is None
    )
    write_tutor("ledger.json", [])
    assert (
        paying_minutes(PhaseState("", "none"), Ledger(), day=DAY, key_file=hmac_key)
        == 0
    )
    assert json.dumps(_theory_credit.MINUTES_PER_CREDIT) == "12"
