"""Tests for the single-instance lock.

The layered wait (``stronger_claims``/``wait_for_turn``) moved to
``gatelock._queue`` and is tested there now -- ``screen_locker`` and
``diet_guard`` needed the same fix leetcode_guard already had, so it no
longer makes sense to keep a leetcode_guard-only copy.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from leetcode_guard import _instance

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_the_first_run_takes_the_lock(tmp_path: Path) -> None:
    """The first acquire of a fresh lock path succeeds."""
    lock = _instance.acquire(tmp_path / "instance.lock")

    assert lock is not None
    lock.release()


def test_a_second_run_stands_down(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Otherwise the afternoon retry stacks a second waiter behind the morning
    one and the gate is cleared twice."""
    path = tmp_path / "instance.lock"
    first = _instance.acquire(path)

    with caplog.at_level(logging.WARNING):
        second = _instance.acquire(path)

    assert first is not None
    assert second is None
    assert any("already holds" in record.message for record in caplog.records)
    first.release()


def test_the_lock_is_retakeable_after_release(tmp_path: Path) -> None:
    """A released lock can be acquired again."""
    path = tmp_path / "instance.lock"
    first = _instance.acquire(path)
    assert first is not None
    first.release()

    second = _instance.acquire(path)

    assert second is not None
    second.release()


def test_an_unopenable_path_reports_failure_rather_than_raising(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A lock path under a regular file returns None instead of raising."""
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")

    with caplog.at_level(logging.ERROR):
        assert _instance.acquire(blocker / "instance.lock") is None


def test_releasing_twice_is_safe(tmp_path: Path) -> None:
    """Releasing an already released lock does not raise."""
    lock = _instance.acquire(tmp_path / "instance.lock")
    assert lock is not None

    lock.release()
    lock.release()


def test_the_lock_file_records_the_pid(tmp_path: Path) -> None:
    """The lock file holds the owning process id."""
    path = tmp_path / "instance.lock"
    lock = _instance.acquire(path)
    assert lock is not None

    assert path.read_text(encoding="utf-8") == str(os.getpid())
    lock.release()


def test_a_close_failure_is_reported_not_raised(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A handle that fails to close is logged as a warning, not raised."""
    lock = _instance.acquire(tmp_path / "instance.lock")
    assert lock is not None

    class Broken:
        """A handle whose close always fails."""

        def close(self) -> None:
            """Fail the way a broken file handle would."""
            message = "cannot close"
            raise OSError(message)

    lock.handle.close()
    lock.handle = Broken()

    with caplog.at_level(logging.WARNING):
        lock.release()

    assert any("could not close" in record.message for record in caplog.records)
