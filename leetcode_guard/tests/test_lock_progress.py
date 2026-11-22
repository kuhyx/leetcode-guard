"""The lock's own poll signs progress while it is up and still short.

The harvester stands aside while a lock holds the instance lock, so this is
the only writer then. Same rules: nothing in the demo, nothing when the lock
may not write, nothing once the day is paid (the charge is the full pay).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from typing import TYPE_CHECKING

import earned_time

from leetcode_guard._daycost import local_today
from leetcode_guard._ledger import to_json
from leetcode_guard._ledger_entries import credit_entry
from leetcode_guard._ledger_io import append, load_ledger
from leetcode_guard.tests._guard_factories import create_guard, probe_of
from leetcode_guard.tests._ledger_fixtures import submission
from leetcode_guard.tests.test_lock_study import locked_guard

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

MONDAY_ROW = "progress:2026-11-23:{}:3"
MONDAY_NOW = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)


def shortfall_guard(tmp_path: Path, key: Path, *new: str, **options):
    """A seeded Monday lock whose next poll brings ``new`` solves (price 3)."""
    guard, _ = create_guard(
        tmp_path,
        probe=probe_of("old-1"),
        poll_probe=probe_of(*new, "old-1"),
        key_file=key,
        seeded=True,
        now=MONDAY_NOW,
        **options,
    )
    return guard


def test_a_solve_that_leaves_the_lock_up_signs_progress(tmp_path: Path, hmac_key: Path):
    """One of three: the row is on disk, signed, and the lock is still up."""
    guard = shortfall_guard(tmp_path, hmac_key, "new-1", demo_mode=False)

    guard.on_poll_result(guard.check())

    assert guard.decision().locked
    ledger = load_ledger(tmp_path / "ledger.json", key_file=hmac_key)
    row = ledger.entries[MONDAY_ROW.format(1)]
    assert row.verified
    assert earned_time.verified(to_json(row), hmac_key.read_bytes().strip())


def test_banked_credit_is_progress_the_moment_the_lock_polls(
    tmp_path: Path, hmac_key: Path
):
    """Nothing new at all, but a credit banked earlier is work done ahead."""
    guard = shortfall_guard(tmp_path, hmac_key, "new-1", demo_mode=False)
    guard.on_poll_result(guard.check())
    guard.check = lambda: probe_of("old-1", "new-1")

    guard.on_poll_result(guard.check())

    ledger = load_ledger(tmp_path / "ledger.json", key_file=hmac_key)
    assert [e.entry_id for e in ledger.of_kind("progress")] == [MONDAY_ROW.format(1)]


def test_a_poll_with_no_credit_at_all_writes_no_row(tmp_path: Path, hmac_key: Path):
    """Nothing done is not progress."""
    guard = shortfall_guard(tmp_path, hmac_key, demo_mode=False)

    guard.on_poll_result(guard.check())

    ledger = load_ledger(tmp_path / "ledger.json", key_file=hmac_key)
    assert not ledger.of_kind("progress")


def test_polling_again_does_not_rewrite_the_ledger(tmp_path: Path, hmac_key: Path):
    """The same numbers are the same row: no write, no snapshot push."""
    guard = shortfall_guard(tmp_path, hmac_key, "new-1", demo_mode=False)
    guard.on_poll_result(guard.check())
    before = (tmp_path / "ledger.json").read_bytes()

    guard.on_poll_result(guard.check())

    assert (tmp_path / "ledger.json").read_bytes() == before


def test_a_paid_day_signs_no_progress(tmp_path: Path, hmac_key: Path):
    """Three of three pays by charge; the lock releases and writes no fraction."""
    guard = shortfall_guard(tmp_path, hmac_key, "n-1", "n-2", "n-3", demo_mode=False)

    guard.on_poll_result(guard.check())

    ledger = load_ledger(tmp_path / "ledger.json", key_file=hmac_key)
    assert ledger.has("charge:2026-11-23")
    assert not ledger.of_kind("progress")


def test_the_demo_lock_signs_no_progress(tmp_path: Path, hmac_key: Path):
    """The demo ledger is thrown away every run; nothing there is a fact."""
    guard = shortfall_guard(tmp_path, hmac_key, "new-1", demo_mode=True)

    guard.on_poll_result(guard.check())

    ledger = load_ledger(tmp_path / "ledger.json", key_file=hmac_key)
    assert not ledger.of_kind("progress")


def test_a_lock_that_may_not_write_signs_no_progress(tmp_path: Path, hmac_key: Path):
    """``write_ledger=False`` means the file stays exactly as it was."""
    guard = shortfall_guard(
        tmp_path, hmac_key, "new-1", demo_mode=False, write_ledger=False
    )
    before = (tmp_path / "ledger.json").read_bytes()

    guard.on_poll_result(guard.check())

    assert (tmp_path / "ledger.json").read_bytes() == before


def test_a_row_that_cannot_be_built_leaves_the_lock_and_the_credit_alone(
    tmp_path: Path,
    hmac_key: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    """The poll finishes: credit banked, lock still up, a warning logged."""
    guard = shortfall_guard(tmp_path, hmac_key, "new-1", demo_mode=False)

    def boom(**_kwargs: object) -> None:
        message = "row builder broke"
        raise ValueError(message)

    monkeypatch.setattr("leetcode_guard._gate_progress.progress_entry", boom)

    with caplog.at_level(logging.WARNING):
        guard.on_poll_result(guard.check())

    ledger = load_ledger(tmp_path / "ledger.json", key_file=hmac_key)
    assert ledger.has("ac:new-1")
    assert guard.decision().locked
    assert any(r.levelno >= logging.WARNING for r in caplog.records)


def test_the_strip_dots_show_banked_progress(tmp_path: Path, hmac_key: Path):
    """0 earned today, 2 banked from Friday, 1 owed: 2 filled and 1 hollow."""
    guard = locked_guard(tmp_path, hmac_key, now=MONDAY_NOW)
    now = guard.deps.moment()
    friday = local_today(now=now) - timedelta(days=3)
    append(
        guard.ledger,
        [
            credit_entry(submission(f"b{n}"), day=friday, now=now, key_file=hmac_key)
            for n in range(2)
        ],
    )
    guard.refresh_strip()

    text = guard.strip_text()

    assert (text.filled, text.hollow) == (2, 1)
