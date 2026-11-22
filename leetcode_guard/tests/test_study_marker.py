"""The restart marker: a runtime file that says study mode was running.

It lives under ``$XDG_RUNTIME_DIR`` (tmpfs, per login), never in the ledger or
under ``~/.local/share``: a study flag in ledger state is the deferral the repo
forbids. The suite points ``XDG_RUNTIME_DIR`` into ``tmp_path`` for every test
(``_paths_fixture``), and the path is read from the environment at call time.
"""

from __future__ import annotations

from datetime import date
import logging
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _study_restart as restart

if TYPE_CHECKING:
    from pathlib import Path

DAY = date(2026, 11, 22)
OTHER_DAY = date(2026, 11, 21)


def _marker(tmp_path: Path) -> Path:
    return tmp_path / "runtime" / "leetcode-guard" / "study.json"


def test_the_suite_redirects_the_marker_into_tmp(tmp_path: Path):
    """A test must never touch the developer's real runtime directory."""
    assert restart.marker_path() == _marker(tmp_path)


def test_a_written_marker_reads_back_for_its_own_day(tmp_path: Path):
    """The round trip: write, then read the same day."""
    assert restart.write_marker(DAY) is True

    assert _marker(tmp_path).is_file()
    assert restart.read_marker(DAY) is True


def test_a_cleared_marker_is_gone(tmp_path: Path):
    """Clear removes the file, and a second clear is harmless."""
    restart.write_marker(DAY)

    restart.clear_marker()
    restart.clear_marker()

    assert not _marker(tmp_path).exists()
    assert restart.read_marker(DAY) is False


def test_a_missing_marker_means_locked_and_is_not_a_warning(
    caplog: pytest.LogCaptureFixture,
):
    """No marker is the ordinary state of every fresh arm: say nothing."""
    with caplog.at_level(logging.WARNING):
        assert restart.read_marker(DAY) is False

    assert caplog.records == []


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        "[]",
        '"study"',
        "{}",
        '{"day": 20261122}',
        '{"day": "not-a-date"}',
        "",
    ],
)
def test_a_corrupt_marker_fails_closed_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, content: str
):
    """Anything that is not exactly the marker we wrote comes back LOCKED."""
    _marker(tmp_path).parent.mkdir(parents=True)
    _marker(tmp_path).write_text(content, encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        assert restart.read_marker(DAY) is False

    assert [r.levelno for r in caplog.records] == [logging.WARNING]


def test_a_non_utf8_marker_fails_closed_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """Undecodable bytes are corruption too, not a crash."""
    _marker(tmp_path).parent.mkdir(parents=True)
    _marker(tmp_path).write_bytes(b"\xff\xfe{")

    with caplog.at_level(logging.WARNING):
        assert restart.read_marker(DAY) is False

    assert len(caplog.records) == 1


def test_a_marker_for_another_day_fails_closed_and_warns(
    caplog: pytest.LogCaptureFixture,
):
    """Yesterday's study session says nothing about today."""
    restart.write_marker(OTHER_DAY)

    with caplog.at_level(logging.WARNING):
        assert restart.read_marker(DAY) is False

    assert [r.levelno for r in caplog.records] == [logging.WARNING]


def test_an_unreadable_marker_fails_closed_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """A directory where the file should be is an OSError, not a crash."""
    _marker(tmp_path).mkdir(parents=True)

    with caplog.at_level(logging.WARNING):
        assert restart.read_marker(DAY) is False

    assert [r.levelno for r in caplog.records] == [logging.WARNING]


@pytest.mark.parametrize("value", [None, "", "relative/dir"])
def test_no_usable_runtime_dir_means_no_marker_anywhere(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    value: str | None,
):
    """Unset, empty or relative ``XDG_RUNTIME_DIR``: nothing is written, nothing
    is read, and the lock comes back LOCKED (a warning says why)."""
    if value is None:
        monkeypatch.delenv("XDG_RUNTIME_DIR")
    else:
        monkeypatch.setenv("XDG_RUNTIME_DIR", value)

    with caplog.at_level(logging.WARNING):
        assert restart.marker_path() is None
        assert restart.write_marker(DAY) is False
        assert restart.read_marker(DAY) is False
        restart.clear_marker()

    assert caplog.records
    assert all(r.levelno >= logging.WARNING for r in caplog.records)


def test_a_failed_write_warns_and_reports_false(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """A runtime dir we cannot write to costs the restart-resume, not the lock."""
    (tmp_path / "runtime").write_text("a file, not a directory", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        assert restart.write_marker(DAY) is False

    assert [r.levelno for r in caplog.records] == [logging.WARNING]


def test_a_failed_clear_warns(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    """A marker that cannot be removed is logged, never raised."""
    _marker(tmp_path).mkdir(parents=True)

    with caplog.at_level(logging.WARNING):
        restart.clear_marker()

    assert [r.levelno for r in caplog.records] == [logging.WARNING]


def test_the_marker_directory_is_private(tmp_path: Path):
    """Own subdirectory, owner-only: nothing else lives next to it."""
    restart.write_marker(DAY)

    assert _marker(tmp_path).parent.stat().st_mode & 0o077 == 0
