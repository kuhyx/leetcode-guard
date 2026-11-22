"""``_run_lock`` and the restart marker.

The marker is read only by a run that has already decided to arm a lock: after
``decide_today`` and after every deferral. It never decides, charges or
settles anything -- the ledger is byte-identical before and after.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from leetcode_guard import _cli
from leetcode_guard import _study_restart as restart
from leetcode_guard._daycost import local_today
from leetcode_guard.tests._net_fixtures import (
    pool_result,
    problem_row,
    recent_ac_result,
    submission_row,
)
from leetcode_guard.tests.test_cli import _seeded_ledger, patch_cli, stub_client

if TYPE_CHECKING:
    from pathlib import Path


class _Guard:
    """Stands in for the lock and records how the CLI drove it."""

    built = 0
    resumed = False
    calls: list[str]

    def __init__(self, **kwargs: Any) -> None:
        type(self).built += 1
        type(self).calls = []
        type(self).resumed = kwargs["deps"].seams.resume_study
        self.lock = SimpleNamespace(grab_input=lambda: type(self).calls.append("grab"))

    def session(self) -> SimpleNamespace:
        """Study is active once ``enter_study`` ran."""
        return SimpleNamespace(active="enter_study" in type(self).calls)

    def enter_study(self, spawn) -> None:
        """Record the re-entry and prove the spawn is a no-op that succeeds."""
        type(self).calls.append("enter_study")
        assert spawn() is True

    def back_to_lock(self) -> None:
        """Record a rollback."""
        type(self).calls.append("back_to_lock")

    def run(self) -> None:
        """Record that the Tk loop would start."""
        type(self).calls.append("run")


@pytest.fixture(name="armed")
def _armed(monkeypatch: pytest.MonkeyPatch, data_dir: Path) -> type[_Guard]:
    """A production run that reaches the guard, with the guard stubbed."""
    _Guard.built = 0
    _Guard.calls = []
    stub_client(
        monkeypatch,
        recent_ac_result([submission_row("1", "solved-already")]),
        pool_result([problem_row("still-open")], total=1),
    )
    patch_cli(monkeypatch, "LeetcodeGuard", _Guard)
    _seeded_ledger(data_dir)
    return _Guard


def test_a_marked_day_re_enters_study_before_the_loop_runs(armed: type[_Guard]):
    """Marker for today: study first, then ``run`` (so the strip and the poll
    are the ordinary ones)."""
    restart.write_marker(local_today())

    assert _cli.main(["--production"]) == 0

    assert armed.calls == ["enter_study", "run"]
    assert armed.resumed is True


def test_resuming_never_touches_the_ledger(armed: type[_Guard], data_dir: Path):
    """A forged marker gains nothing: no charge, no settled day, no credit."""
    before = (data_dir / "ledger.json").read_bytes()
    restart.write_marker(local_today())

    _cli.main(["--production"])

    assert armed.calls == ["enter_study", "run"]
    assert (data_dir / "ledger.json").read_bytes() == before


def test_no_marker_arms_locked(armed: type[_Guard]):
    """The ordinary run: the guard comes up locked and only runs."""
    _cli.main(["--production"])

    assert armed.calls == ["run"]
    assert armed.resumed is False


def test_a_marker_for_another_day_arms_locked(armed: type[_Guard]):
    """Yesterday's marker (a long-lived runtime dir) is not today's study."""

    restart.write_marker(local_today() - timedelta(days=1))

    _cli.main(["--production"])

    assert armed.calls == ["run"]


def test_a_corrupt_marker_arms_locked(armed: type[_Guard]):
    """Fail closed on anything but a valid marker."""
    path = restart.marker_path()
    path.parent.mkdir(parents=True)
    path.write_text("{truncated", encoding="utf-8")

    _cli.main(["--production"])

    assert armed.calls == ["run"]


def test_no_runtime_dir_arms_locked(armed: type[_Guard], monkeypatch):
    """``XDG_RUNTIME_DIR`` unset: nothing to read, so locked."""
    monkeypatch.delenv("XDG_RUNTIME_DIR")

    _cli.main(["--production"])

    assert armed.calls == ["run"]


def test_a_demo_run_ignores_the_marker(armed: type[_Guard]):
    """The demo must never inherit a production study session."""
    restart.write_marker(local_today())

    _cli.main([])

    assert armed.calls == ["run"]


def test_a_deferred_run_does_not_read_the_marker(
    armed: type[_Guard], monkeypatch: pytest.MonkeyPatch
):
    """After every deferral: a run that does not arm never looks at it."""
    restart.write_marker(local_today())
    patch_cli(monkeypatch, "defer_for_evening_lockdown", lambda _now: "tonight")
    seen: list[object] = []

    def spy(day: object) -> bool:
        seen.append(day)
        return True

    monkeypatch.setattr(restart, "read_marker", spy)

    _cli.main(["--production"])

    assert armed.built == 0
    assert seen == []
