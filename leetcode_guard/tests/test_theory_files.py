"""Tutor files that are not safe to open: unstat-able, not regular, too big.

The reader ``stat``s before it opens, so none of these may ever reach ``open``
(a FIFO with no writer would block the arming run forever). Continued from
:mod:`leetcode_guard.tests.test_theory_hostile`, split for the 250-line cap.
"""

from __future__ import annotations

import builtins
import os
from pathlib import Path
import stat
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _tutor_read
from leetcode_guard._curriculum import Theory
from leetcode_guard.tests.test_theory import states as theory_states
from leetcode_guard.tests.test_theory import tutor_dir
from leetcode_guard.tests.test_theory_hostile import (
    BITS_DONE,
    append,
    warnings_about,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import BinaryIO


def refuse_open(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """Fail the test the moment the reader opens ``name``, hang-proof."""

    def guarded(
        path: Path, mode: str, *, opener: Callable[[str, int], int]
    ) -> BinaryIO:
        if Path(path).name == name:
            msg = f"the reader opened {name}, which it must only stat"
            raise AssertionError(msg)
        return builtins.open(path, mode, opener=opener)

    monkeypatch.setattr(_tutor_read, "open", guarded, raising=False)


def tutor_file(root: Path, name: str) -> Path:
    """Where the tutor keeps ``name`` for the ``algo`` subject."""
    return root / name if name == "log.jsonl" else root / "subjects/algo" / name


@pytest.mark.parametrize("name", ["cards.json", "log.jsonl"])
def test_an_unstatable_file_is_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    name: str,
):
    """A tutor dir kuhy cannot search (``PermissionError``) is an unreadable file."""
    root = tutor_dir(tmp_path, *BITS_DONE)
    real_stat = Path.stat

    def deny(self: Path, **kwargs: bool) -> os.stat_result:
        if self.name == name:
            raise PermissionError(13, "Permission denied", str(self))
        return real_stat(self, **kwargs)

    monkeypatch.setattr(Path, "stat", deny)

    with caplog.at_level("WARNING"):
        assert theory_states(root)[1] is Theory.UNKNOWN

    assert len(warnings_about(caplog, str(tutor_file(root, name)))) == 1


@pytest.mark.parametrize("name", ["cards.json", "log.jsonl"])
@pytest.mark.parametrize("make", [os.mkfifo, Path.mkdir], ids=["fifo", "directory"])
def test_a_file_that_is_not_regular_is_never_opened(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    name: str,
    make: Callable[[Path], object],
):
    """A FIFO with no writer would block the arming run forever on ``open``."""
    root = tutor_dir(tmp_path, *BITS_DONE)
    target = tutor_file(root, name)
    target.unlink()
    make(target)
    refuse_open(monkeypatch, name)

    with caplog.at_level("WARNING"):
        assert theory_states(root)[1] is Theory.UNKNOWN

    assert len(warnings_about(caplog, str(tutor_file(root, name)))) == 1


@pytest.mark.parametrize("name", ["cards.json", "log.jsonl"])
def test_an_oversized_file_is_never_opened(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    name: str,
):
    """Past the cap the file is one more thing we cannot check."""
    root = tutor_dir(tmp_path, *BITS_DONE)
    monkeypatch.setattr(_tutor_read, "MAX_TUTOR_FILE_BYTES", 1_000)
    tutor_file(root, name).write_bytes(b" " * 2_000)
    refuse_open(monkeypatch, name)

    with caplog.at_level("WARNING"):
        assert theory_states(root)[1] is Theory.UNKNOWN

    assert len(warnings_about(caplog, str(tutor_file(root, name)))) == 1


def test_a_file_that_grows_past_the_cap_after_the_stat_is_still_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    """The stat said small, the append said otherwise: the read is capped too."""
    root = tutor_dir(tmp_path, *BITS_DONE)
    monkeypatch.setattr(_tutor_read, "MAX_TUTOR_FILE_BYTES", 60)
    real_stat = Path.stat
    small = os.stat_result((stat.S_IFREG | 0o600, 0, 0, 1, 0, 0, 1, 0, 0, 0))

    def stale(self: Path, **kwargs: bool) -> os.stat_result:
        return small if self.name == "log.jsonl" else real_stat(self, **kwargs)

    monkeypatch.setattr(Path, "stat", stale)
    append(root, b"x" * 100)

    with caplog.at_level("WARNING"):
        assert theory_states(root)[1] is Theory.UNKNOWN

    assert len(warnings_about(caplog, "log.jsonl")) == 1


def test_the_cap_is_generous_against_the_real_log():
    """The real log was 181 KB on 2026-11-21; the cap must not trip on growth."""
    assert _tutor_read.MAX_TUTOR_FILE_BYTES >= 100 * 181_000
