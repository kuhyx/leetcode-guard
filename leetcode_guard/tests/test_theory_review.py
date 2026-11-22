"""Review minutes share the 12-minute counter with lesson minutes (kuhy 2026-11-22).

The scenario is ``_theory_scenario``'s: unit ``a`` (module ``a``, Easy ``a1``)
then unit ``b`` (modules ``b1``, ``b2``). A review row on any mapped card pays
one for one, in every phase, whatever the current unit. Invariants I1-I8.
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from leetcode_guard import _tutor_signed
from leetcode_guard._ledger_entries import credit_entry
from leetcode_guard._ledger_io import Ledger, append, load_ledger
from leetcode_guard._theory_credit import minutes_into_credit
from leetcode_guard._tutor_minutes import teaching_minutes
from leetcode_guard.tests._ledger_fixtures import submission
from leetcode_guard.tests._review_fixtures import (
    DAY,
    NOW,
    finish_unit_a,
    lessons,
    poll,
    put,
    reviews,
    theory_rows,
)
from leetcode_guard.tests._theory_scenario import began, states, world
from leetcode_guard.tests._tutor_fixtures import ALGO, review_row

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_i1_10_lesson_plus_2_review_minutes_pay_one_credit(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """THEORY(a): 10 lesson minutes + 2 review minutes on b's card = 12 = 1 credit."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    began(hmac_key)
    put(lessons(hmac_key, "a", 10), reviews(hmac_key, "b1", 2))
    ledger = Ledger()

    result = poll(ledger, data_dir, hmac_key)

    assert result.minutes == 12
    assert theory_rows(ledger) == [("a", "12", "2")]
    assert poll(ledger, data_dir, hmac_key).minted == ()


def test_i2_24_review_minutes_pay_two_credits_in_solve(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """SOLVE(a): nothing teachable, no lesson minutes; 24 review minutes pay 2."""
    world(tmp_path, monkeypatch)
    states(hmac_key, "a")
    put(reviews(hmac_key, "b2", 24))
    ledger = Ledger()

    result = poll(ledger, data_dir, hmac_key)

    assert result.state is not None
    assert (result.state.unit, result.state.phase) == ("a", "solve")
    assert theory_rows(ledger) == [("a", "12", "12"), ("a", "24", "24")]


def test_i2_24_review_minutes_pay_two_credits_labelled_review_in_none(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """Every unit finished: reviews still pay, under the label ``review``."""
    world(tmp_path, monkeypatch)
    ledger = finish_unit_a(data_dir, hmac_key)
    states(hmac_key, "a", "b1", "b2")
    append(
        ledger,
        [credit_entry(submission("2", "b1-easy"), day=DAY, now=NOW, key_file=hmac_key)],
    )
    put(reviews(hmac_key, "a", 24))

    result = poll(ledger, data_dir, hmac_key)

    assert result.state is not None
    assert result.state.phase == "none"
    assert theory_rows(ledger) == [("review", "12", "12"), ("review", "24", "24")]
    assert minutes_into_credit(ledger, result.state, 30, day=DAY) == 6


def test_i3_a_unit_change_never_re_pays_reviews(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """24 reviews under a mint 2; unit b with no lessons mints 0; 36 mints 1 more."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    began(hmac_key)
    put(reviews(hmac_key, "b1", 24))
    ledger = Ledger()
    poll(ledger, data_dir, hmac_key)
    assert [row[0] for row in theory_rows(ledger)] == ["a", "a"]

    ledger = finish_unit_a(data_dir, hmac_key)
    moved = poll(ledger, data_dir, hmac_key)

    assert moved.state is not None
    assert moved.state.unit == "b"
    assert [m.entry_id for m in moved.minted if m.entry_id.startswith("theory:")] == []

    put(reviews(hmac_key, "b1", 36))
    poll(ledger, data_dir, hmac_key)

    assert [row[0] for row in theory_rows(ledger)] == ["a", "a", "b"]
    assert theory_rows(ledger)[2] == ("b", "12", "12")


def test_i4_a_unit_change_never_eats_lesson_backed_credits(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """a had 24 lesson minutes (2 credits, 0 reviews spent); b then gets 12 reviews: 1."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    began(hmac_key)
    put(lessons(hmac_key, "a", 24))
    ledger = Ledger()
    poll(ledger, data_dir, hmac_key)
    assert theory_rows(ledger) == [("a", "12", "0"), ("a", "24", "0")]

    ledger = finish_unit_a(data_dir, hmac_key)
    assert poll(ledger, data_dir, hmac_key).minted == ()
    put(lessons(hmac_key, "a", 24), reviews(hmac_key, "b1", 12))
    poll(ledger, data_dir, hmac_key)

    assert theory_rows(ledger)[2:] == [("b", "12", "12")]
    assert len(theory_rows(ledger)) == 3


def test_i5_a_twin_pays_once_and_nothing_untagged_or_unmapped_or_old_pays(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """Twin (untagged + tagged, one entry_id) = its minutes once; the rest pay 0."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    began(hmac_key)
    yesterday = NOW - timedelta(days=1)
    forged = review_row("forged-m1", 7, ended=NOW, key_file=hmac_key)
    forged["hmac"] = "0" + str(forged["hmac"])
    put(
        [review_row("twin-m1", 2, ended=NOW, key_file=hmac_key, where=None)],
        [review_row("twin-m1", 5, ended=NOW, key_file=hmac_key)],
        [review_row("lone-m1", 9, ended=NOW, key_file=hmac_key, where=None)],
        [forged],
        [review_row("odd-m1", 9, ended=NOW, key_file=hmac_key, where=(ALGO, "zz"))],
        [review_row("old-m1", 9, ended=yesterday, key_file=hmac_key)],
    )

    assert poll(Ledger(), data_dir, hmac_key).minutes == 5


def teaching_total(key: Path) -> int:
    """What ``teaching_minutes`` alone counts for a's module from the scratch file."""
    rows = _tutor_signed.signed_rows("ledger.json", key_file=key)
    assert rows is not None
    return teaching_minutes(rows, ALGO, ("a",), day=DAY)


def test_i6_a_tagged_review_on_the_current_unit_counts_once(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """THEORY(a): 6 lesson + 6 review minutes on a's own module = 12, not 18."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    began(hmac_key)
    put(lessons(hmac_key, "a", 6), reviews(hmac_key, "a", 6))

    result = poll(Ledger(), data_dir, hmac_key)

    assert result.minutes == 12
    assert len(result.minted) == 1
    assert teaching_total(hmac_key) == 6


def test_i7_deleting_the_guard_ledger_re_mints_at_most_todays_credits(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """24 reviews today and 36 yesterday: a deleted ledger still ends at 2 credits."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    began(hmac_key)
    old = [
        review_row(
            f"y{i}", 1, ended=NOW - timedelta(days=1, minutes=i), key_file=hmac_key
        )
        for i in range(36)
    ]
    put(reviews(hmac_key, "b1", 24), old)
    ledger = Ledger()
    poll(ledger, data_dir, hmac_key)
    (data_dir / "ledger.json").unlink()
    fresh = Ledger()

    poll(fresh, data_dir, hmac_key)

    assert theory_rows(fresh) == theory_rows(ledger)
    assert len(load_ledger(data_dir / "ledger.json", key_file=hmac_key).entries) == 2


def test_i8_an_unreadable_tutor_ledger_mints_nothing_and_warns(
    tmp_path,
    monkeypatch,
    data_dir: Path,
    hmac_key: Path,
    caplog: pytest.LogCaptureFixture,
):
    """Cannot check is not 0 reviews: in ``none`` too, where the file was never read."""
    world(tmp_path, monkeypatch)
    ledger = finish_unit_a(data_dir, hmac_key)
    states(hmac_key, "a", "b1", "b2")
    append(
        ledger,
        [credit_entry(submission("2", "b1-easy"), day=DAY, now=NOW, key_file=hmac_key)],
    )
    (_tutor_signed.TUTOR_DIR / "ledger.json").write_text("{torn", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        result = poll(ledger, data_dir, hmac_key)

    assert result.state is not None
    assert result.state.phase == "none"
    assert (result.minted, theory_rows(ledger)) == ((), [])
    assert "cannot check" in caplog.text
