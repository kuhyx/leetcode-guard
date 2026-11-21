"""The theory snapshot of the ``attempts:`` line: fixed at solve time, once."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from leetcode_guard import _attempt_line
from leetcode_guard._attempt_store import load, merge_submissions
from leetcode_guard._ledger import SEEN
from leetcode_guard.tests._attempt_helpers import DAY, SECONDS_PER_DAY, T0
from leetcode_guard.tests._attempt_line_helpers import (
    BITS_TAUGHT,
    credit,
    line,
    put_ledger,
    put_pool,
    theory_of,
)
from leetcode_guard.tests.test_theory import tutor_dir
from leetcode_guard.tests.test_theory_surface import TREE_CARDS, TREES_TAUGHT, use

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_a_solve_fixes_the_theory_state_of_its_day(
    hmac_key: Path,
    data_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Taught at solve time reads ``done`` and stays ``done`` after the tutor moves."""
    use(tmp_path, monkeypatch, tutor_dir(tmp_path / "t1", *BITS_TAUGHT))
    put_pool(data_dir)
    put_ledger(data_dir, credit("5", "bit-trick", T0 - 3600, hmac_key))

    assert line(hmac_key) == "1 snapshot"

    assert theory_of("bit-trick") == "done"
    stored = load()[f"{DAY}|bit-trick"].submissions
    assert (stored["5"].status, stored["5"].at) == ("Accepted", T0 - 3600)

    use(tmp_path, monkeypatch, tutor_dir(tmp_path / "t2"))
    assert line(hmac_key) == "idle"
    assert theory_of("bit-trick") == "done"


def test_each_state_of_the_unit_is_stored_as_its_value(
    hmac_key: Path,
    data_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """pending (unit mapped, untaught), none (unit with no tutor module)."""
    use(
        tmp_path,
        monkeypatch,
        tutor_dir(tmp_path / "t", *TREES_TAUGHT, cards=TREE_CARDS),
    )
    put_pool(data_dir)
    put_ledger(
        data_dir,
        credit("1", "bit-trick", T0 - 60, hmac_key),
        credit("2", "plain-scan", T0 - 50, hmac_key),
        credit("3", "tree-walk", T0 - 40, hmac_key),
    )

    assert line(hmac_key) == "3 snapshots"

    assert theory_of("bit-trick") == "pending"
    assert theory_of("plain-scan") == "none"
    assert theory_of("tree-walk") == "done"


def test_a_slug_missing_from_the_pool_is_stored_unknown(
    hmac_key: Path, data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Not in the pool cache: its tags are unknown, so is its theory."""
    use(tmp_path, monkeypatch, tutor_dir(tmp_path / "t", *BITS_TAUGHT))
    put_ledger(data_dir, credit("1", "ghost", T0 - 60, hmac_key))

    assert line(hmac_key) == "1 snapshot"
    assert theory_of("ghost") == "unknown"


def test_no_curriculum_is_stored_unknown(hmac_key: Path, data_dir: Path):
    """The default test curriculum file does not exist: no units, no answer."""
    put_pool(data_dir)
    put_ledger(data_dir, credit("1", "bit-trick", T0 - 60, hmac_key))

    assert line(hmac_key) == "1 snapshot"
    assert theory_of("bit-trick") == "unknown"


def test_a_theory_reader_that_raises_costs_only_the_value(
    hmac_key: Path,
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    """The fence: ``unknown`` and a warning, and the record is still made."""

    def explode() -> object:
        message = "boom"
        raise RuntimeError(message)

    monkeypatch.setattr(_attempt_line, "load_blocks", explode)
    put_pool(data_dir)
    put_ledger(data_dir, credit("1", "bit-trick", T0 - 60, hmac_key))

    with caplog.at_level(logging.WARNING):
        assert line(hmac_key) == "1 snapshot"

    assert theory_of("bit-trick") == "unknown"
    assert "RuntimeError" in caplog.text


def test_only_the_earliest_credit_of_a_slug_is_its_solve(
    hmac_key: Path, data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A re-solve of an old problem is not a new solve; its day gets no snapshot."""
    use(tmp_path, monkeypatch, tutor_dir(tmp_path / "t", *BITS_TAUGHT))
    put_pool(data_dir)
    put_ledger(
        data_dir,
        credit("9", "bit-trick", T0 - 5 * SECONDS_PER_DAY, hmac_key),
        credit("10", "bit-trick", T0 - 60, hmac_key),
    )

    assert line(hmac_key) == "idle"
    assert load() == {}


def test_a_solve_older_than_two_days_is_left_alone(
    hmac_key: Path, data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The window: a snapshot is only taken close to the solve."""
    use(tmp_path, monkeypatch, tutor_dir(tmp_path / "t", *BITS_TAUGHT))
    put_pool(data_dir)
    put_ledger(
        data_dir, credit("9", "bit-trick", T0 - 2 * SECONDS_PER_DAY - 1, hmac_key)
    )

    assert line(hmac_key) == "idle"
    assert load() == {}


def test_ledger_rows_without_the_fields_are_skipped(
    hmac_key: Path, data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Markers, foreign ids and rows lacking a slug or a timestamp are not solves."""
    use(tmp_path, monkeypatch, tutor_dir(tmp_path / "t", *BITS_TAUGHT))
    put_pool(data_dir)
    at = str(T0 - 60)
    put_ledger(
        data_dir,
        credit("1", "bit-trick", T0 - 60, hmac_key, kind=SEEN),
        credit("2", "bit-trick", T0 - 60, hmac_key, entry_id="charge:2026-11-21"),
        credit("3", "bit-trick", T0 - 60, hmac_key, title_slug=""),
        credit("4", "bit-trick", T0 - 60, hmac_key, submitted_at="soon"),
        credit("5", "bit-trick", T0 - 60, hmac_key, submitted_at="-" + at),
        credit("6", "tree-walk", T0 - 60, hmac_key, submitted_at=""),
    )

    assert line(hmac_key) == "idle"
    assert load() == {}


def test_a_record_with_a_snapshot_is_not_rewritten(
    hmac_key: Path, data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Set once: a later run with a different tutor state changes nothing."""
    use(tmp_path, monkeypatch, tutor_dir(tmp_path / "t"))
    put_pool(data_dir)
    put_ledger(data_dir, credit("5", "bit-trick", T0 - 60, hmac_key))
    merge_submissions([("5", "bit-trick", "Accepted", T0 - 60)], now=T0)
    assert line(hmac_key) == "1 snapshot"
    assert theory_of("bit-trick") == "pending"

    use(tmp_path, monkeypatch, tutor_dir(tmp_path / "t2", *BITS_TAUGHT))

    assert line(hmac_key) == "idle"
    assert theory_of("bit-trick") == "pending"
