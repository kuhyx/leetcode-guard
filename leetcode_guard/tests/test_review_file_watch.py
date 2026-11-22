"""The review file watch: a rewritten ``review_due.json`` brings the poll forward.

A fake clock and a counting ``stat`` seam, over a real scratch directory: the
tutor's write is a temp file plus a rename, so the test does the same.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _tutor_signed
from leetcode_guard._review_file_watch import DueFileWatch

if TYPE_CHECKING:
    import os
    from pathlib import Path


class Clock:
    """A monotonic clock the test moves by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class CountingStat:
    """``os.stat`` that counts its calls, and may be told to raise."""

    def __init__(self) -> None:
        self.calls = 0
        self.raises: BaseException | None = None

    def __call__(self, path: Path) -> os.stat_result:
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return path.stat()


class Rig:
    """A watch over a scratch tutor dir, with its clock, stat and gate."""

    def __init__(self, tutor_dir: Path) -> None:
        self.dir = tutor_dir
        self.clock = Clock()
        self.stat = CountingStat()
        self.on = True
        self.watch = DueFileWatch(lambda: self.on, clock=self.clock, stat=self.stat)

    def write(self, text: str) -> None:
        """Replace the file the way the tutor does: temp file, then rename."""
        self.dir.mkdir(parents=True, exist_ok=True)
        temp = self.dir / "review_due.json.tmp"
        temp.write_text(text, encoding="utf-8")
        temp.replace(self.dir / "review_due.json")

    def tick(self, seconds: float = 0.02) -> bool:
        """Advance the clock and run one watch step."""
        self.clock.now += seconds
        return self.watch()


@pytest.fixture(name="rig")
def _rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    tutor = tmp_path / "tutor-watch"
    monkeypatch.setattr(_tutor_signed, "TUTOR_DIR", tutor)
    return Rig(tutor)


def test_the_first_observation_only_records(rig: Rig) -> None:
    """The lock has just read the file: no extra poll at t=0."""
    rig.write("a")

    assert rig.watch() is False
    assert rig.stat.calls == 1


def test_a_rename_over_the_file_asks_for_exactly_one_poll(rig: Rig) -> None:
    """Rewritten by rename: one request, then quiet while it stays put."""
    rig.write("a")
    rig.watch()
    rig.write("a")  # same bytes, new inode: still a rewrite

    asked = [rig.tick(0.25) for _ in range(40)]

    assert asked.count(True) == 1
    assert asked.index(True) == 3  # the first step a full second after the prime


def test_an_unchanged_file_never_asks(rig: Rig) -> None:
    """Many ticks, nothing rewritten: no request."""
    rig.write("a")
    rig.watch()

    assert not any(rig.tick(0.02) for _ in range(500))


def test_at_most_one_stat_per_second(rig: Rig) -> None:
    """640 steps of 1/64 s is ten seconds: eleven stats, not 640."""
    rig.write("a")
    rig.watch()

    for _ in range(640):
        rig.tick(1 / 64)

    assert rig.stat.calls == 11


def test_idle_cost_is_sixty_stats_a_minute(rig: Rig) -> None:
    """The rough cost check: a minute of ~16 ms loop steps (the real one is 20)."""
    rig.write("a")
    rig.watch()
    rig.stat.calls = 0

    for _ in range(3840):
        rig.tick(1 / 64)

    assert rig.stat.calls == 60


def test_two_changes_inside_a_second_are_both_seen_eventually(rig: Rig) -> None:
    """The gate defers the stat; the later change is not lost."""
    rig.write("a")
    rig.watch()
    rig.write("b")
    assert rig.tick(1.0) is True
    seen = rig.stat.calls

    rig.write("c")
    assert rig.tick(0.3) is False  # inside the second: no stat at all
    assert rig.stat.calls == seen
    assert rig.tick(0.8) is True  # the next stat sees the second change
    assert rig.stat.calls == seen + 1
    assert rig.tick(1.0) is False


def test_a_missing_file_is_silent_and_never_asks(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    """Absent is a signature, not an error: no request, no log line (ENOENT)."""
    with caplog.at_level(logging.DEBUG):
        asked = [rig.tick(1.0) for _ in range(5)]

    assert not any(asked)
    assert caplog.records == []


def test_a_file_that_appears_later_asks_once(rig: Rig) -> None:
    """Absent, then written: one request."""
    rig.tick(1.0)
    rig.write("a")

    asked = [rig.tick(1.0) for _ in range(4)]

    assert asked == [True, False, False, False]


def test_a_file_that_disappears_asks_once(rig: Rig) -> None:
    """Deleted is a change too (the lock then reads "cannot check")."""
    rig.write("a")
    rig.watch()
    (rig.dir / "review_due.json").unlink()

    asked = [rig.tick(1.0) for _ in range(3)]

    assert asked == [True, False, False]


def test_a_failing_stat_is_absent_not_an_error(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    """PermissionError and friends: absent, one warning per run; back asks once."""
    rig.write("a")
    rig.watch()
    rig.stat.raises = PermissionError("locked")

    with caplog.at_level(logging.DEBUG):
        first = [rig.tick(1.0) for _ in range(3)]
    rig.stat.raises = None
    back = [rig.tick(1.0) for _ in range(2)]

    assert first == [True, False, False]  # present -> absent is a change
    assert back == [True, False]
    assert len(caplog.records) == 1  # three failing seconds, one line


def test_an_inactive_watch_never_stats(rig: Rig) -> None:
    """Demo, or a phase with no review targets: not one ``stat``."""
    rig.write("a")
    rig.on = False

    assert not any(rig.tick(1.0) for _ in range(50))
    assert rig.stat.calls == 0


def test_turning_active_again_starts_with_a_fresh_observation(rig: Rig) -> None:
    """The poll that brought the phase back just read the file: record only."""
    rig.write("a")
    rig.watch()
    rig.on = False
    rig.tick(1.0)
    rig.write("b")
    rig.on = True

    assert rig.tick(1.0) is False
    assert rig.tick(1.0) is False


def test_the_path_is_resolved_at_call_time(
    rig: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pointing the tutor dir elsewhere after construction is honoured."""
    rig.write("a")
    rig.watch()
    other = Rig(tmp_path / "other-tutor")
    monkeypatch.setattr(_tutor_signed, "TUTOR_DIR", other.dir)
    other.write("x")

    assert rig.tick(1.0) is True  # the file under the new dir differs from the old


def test_an_unexpected_exception_warns_once_and_the_watch_survives(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    """Not an OSError: caught at the boundary, one logged line per run, no raise."""
    rig.write("a")
    rig.watch()
    rig.stat.raises = RuntimeError("boom")

    with caplog.at_level(logging.WARNING):
        asked = [rig.tick(1.0) for _ in range(5)]

    assert not any(asked)
    logged = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(logged) == 1
    assert logged[0].exc_info is not None
    rig.stat.raises = None
    rig.write("b")
    assert rig.tick(1.0) is True  # still alive, and still watching
