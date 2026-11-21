"""Tests for the fail-open paths and for two writers sharing the file."""

from __future__ import annotations

import fcntl
import logging
import threading
from typing import TYPE_CHECKING
from unittest.mock import patch

from leetcode_guard import _attempt_io
from leetcode_guard._attempt_lock import LockTiming
from leetcode_guard._attempt_store import Outcome, add_beat, load, merge_submissions
from leetcode_guard.tests._attempt_helpers import (
    DAY,
    KEY,
    T0,
    attempts_path,
    hold_lock,
    virtual_timing,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_a_held_lock_skips_the_write_after_two_seconds(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The wait is virtual: the injected clock reaches the deadline."""
    timing, slept = virtual_timing()

    with hold_lock(attempts_path()), caplog.at_level(logging.WARNING):
        result = add_beat("two-sum", "description", now=T0, timing=timing)

    assert result is Outcome.FAILED
    assert 1.9 < sum(slept) < 2.5
    assert "lock" in caplog.text
    assert not attempts_path().exists()


def test_a_lock_freed_during_the_wait_is_taken() -> None:
    """Contention that clears inside the window still writes."""
    with hold_lock(attempts_path()) as held:

        def release(_seconds: float) -> None:
            fcntl.flock(held, fcntl.LOCK_UN)

        timing = LockTiming(sleep=release, monotonic=iter(range(100)).__next__)

        result = add_beat("two-sum", "description", now=T0, timing=timing)

    assert result is Outcome.WRITTEN
    assert set(load()) == {KEY}


def test_an_uncreatable_lock_file_fails_open(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No lock file, no write, one warning."""
    with (
        patch("leetcode_guard._attempt_lock.os.open", side_effect=OSError("ro")),
        caplog.at_level(logging.WARNING),
    ):
        assert add_beat("two-sum", "description", now=T0) is Outcome.FAILED

    assert "lock" in caplog.text


def test_a_failed_parent_directory_fails_open(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """A data dir that cannot exist is a warning too."""
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        result = add_beat("a", "description", now=T0, path=blocker / "attempts.json")

    assert result is Outcome.FAILED


def test_a_corrupt_file_is_set_aside_and_replaced(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Measurement must not stall forever on one bad file."""
    path = attempts_path()
    path.write_text("{garbage", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        assert add_beat("two-sum", "description", now=T0) is Outcome.WRITTEN

    assert path.with_name("attempts.json.corrupt").read_text() == "{garbage"
    assert set(load()) == {KEY}
    assert "corrupt" in caplog.text


def test_a_newer_corrupt_file_overwrites_the_older_aside() -> None:
    """One aside slot: the latest bad file wins."""
    path = attempts_path()
    aside = path.with_name("attempts.json.corrupt")
    aside.write_text("old", encoding="utf-8")
    path.write_text("[1, 2]", encoding="utf-8")

    add_beat("two-sum", "description", now=T0)

    assert aside.read_text(encoding="utf-8") == "[1, 2]"


def test_an_aside_that_cannot_be_made_still_starts_fresh(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A blocked aside is a second warning, not a stalled writer."""
    path = attempts_path()
    (path.with_name("attempts.json.corrupt") / "keep").mkdir(parents=True)
    path.write_text("{garbage", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        assert add_beat("two-sum", "description", now=T0) is Outcome.WRITTEN

    assert set(load()) == {KEY}
    assert "aside" in caplog.text


def test_a_failed_write_warns_and_reports_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """OSError from the atomic write never reaches the caller."""
    with (
        patch.object(_attempt_io, "write_json", side_effect=OSError("full")),
        caplog.at_level(logging.WARNING),
    ):
        assert add_beat("two-sum", "description", now=T0) is Outcome.FAILED
        assert merge_submissions([("1", "two-sum", "Accepted", T0)], now=T0) == 0

    assert "write" in caplog.text


def test_parallel_writers_keep_every_beat() -> None:
    """Eight threads, one read-modify-write each, all survive."""
    slugs = [f"problem-{index}" for index in range(8)]
    timing = LockTiming(interval=0.001, timeout=20.0)
    results: list[Outcome] = []

    def work(slug: str) -> None:
        results.append(add_beat(slug, "description", now=T0, timing=timing))

    threads = [threading.Thread(target=work, args=(slug,)) for slug in slugs]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == [Outcome.WRITTEN] * 8
    assert set(load()) == {f"{DAY}|{slug}" for slug in slugs}
