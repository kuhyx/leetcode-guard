"""A restart must not change whether the lock is in study mode.

SIGTERM runs ``on_close``, which winds study mode down to free the grab and VT
switching; that must leave the marker, or a restart can never resume. Only a
real end (Back to lock, a landed solve) removes it. The restarted process reads
it and re-enters study through the ordinary ``enter_study`` path.
"""

from __future__ import annotations

from dataclasses import replace
import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from leetcode_guard import _lock_study as lock_study
from leetcode_guard import _study_restart as restart
from leetcode_guard._gatelock_internals import arming, set_arming, start_stepback
from leetcode_guard.tests._guard_factories import create_guard, probe_of
from leetcode_guard.tests._ledger_fixtures import NOW
from leetcode_guard.tests.test_lock_study import URL, locked_guard

if TYPE_CHECKING:
    from pathlib import Path

    from leetcode_guard._lock import LeetcodeGuard

DAY = NOW.date()


def _studying(tmp_path: Path, hmac_key: Path, **kwargs) -> LeetcodeGuard:
    """A production guard that has pressed Open (needs ``no_spawn``)."""
    guard = locked_guard(tmp_path, hmac_key, demo_mode=False, **kwargs)
    guard.open_problem(URL)
    return guard


@pytest.mark.usefixtures("no_spawn")
def test_open_writes_the_marker_for_today(tmp_path: Path, hmac_key: Path):
    """Entering study leaves the restart marker, dated by the guard's clock."""
    _studying(tmp_path, hmac_key)

    assert restart.read_marker(DAY) is True


@pytest.mark.usefixtures("no_spawn")
def test_a_demo_lock_never_writes_the_marker(tmp_path: Path, hmac_key: Path):
    """A demo SIGTERMed mid-study must not make the next production arm skip
    its grab."""
    guard = locked_guard(tmp_path, hmac_key, demo_mode=True)

    guard.open_problem(URL)

    assert restart.marker_path() is not None
    assert not restart.marker_path().exists()


@pytest.mark.usefixtures("no_spawn")
def test_an_evening_lock_never_writes_the_marker(tmp_path: Path, hmac_key: Path):
    """The evening chain relaunches its own rungs; it is not a morning restart."""
    guard, _ = create_guard(
        tmp_path,
        evening=True,
        demo_mode=False,
        seeded=True,
        probe=probe_of("old-1"),
        key_file=hmac_key,
    )
    set_arming(
        guard.lock,
        replace(arming(guard.lock), recovery=MagicMock(), detector=MagicMock()),
    )

    guard.open_problem(URL)

    assert guard.session().active
    assert not restart.marker_path().exists()


def test_a_failed_launch_rolls_back_without_a_marker(
    tmp_path: Path, hmac_key: Path, monkeypatch: pytest.MonkeyPatch
):
    """Nothing to study with means the lock comes back; nothing to resume to."""
    guard = locked_guard(tmp_path, hmac_key, demo_mode=False)
    monkeypatch.setattr(lock_study, "find_opener", lambda: "/bin/true")
    monkeypatch.setattr(
        lock_study, "launch", lambda _url: SimpleNamespace(ok=False, reason="gone")
    )

    guard.open_problem(URL)

    assert not guard.session().active
    assert not restart.marker_path().exists()


@pytest.mark.usefixtures("no_spawn")
def test_back_to_lock_removes_the_marker(tmp_path: Path, hmac_key: Path):
    """The user chose the lock back: a restart must not undo that."""
    guard = _studying(tmp_path, hmac_key)

    guard.back_to_lock()

    assert not guard.session().active
    assert not restart.marker_path().exists()


@pytest.mark.usefixtures("no_spawn")
def test_sigterm_leaves_the_marker_and_re_locks_nothing(tmp_path: Path, hmac_key: Path):
    """``on_close`` is every exit path, SIGTERM included. Leaving while study is
    remembered must not re-lock or grab (the next start decides), and the
    marker stays so that start can resume."""
    guard = _studying(tmp_path, hmac_key)
    grabs = guard.lock.root.grab_set_global.call_count

    guard.on_close()

    assert guard.lock.root.grab_set_global.call_count == grabs
    assert guard.strip is None
    assert restart.read_marker(DAY) is True


@pytest.mark.usefixtures("no_spawn")
def test_a_demo_lock_still_re_locks_on_exit(tmp_path: Path, hmac_key: Path):
    """Nothing is remembered for a demo, so the old exit applies."""
    guard = locked_guard(tmp_path, hmac_key, demo_mode=True)
    guard.open_problem(URL)

    guard.on_close()

    assert not guard.session().active


@pytest.mark.usefixtures("no_spawn")
def test_a_landed_solve_removes_the_marker(tmp_path: Path, hmac_key: Path):
    """A solve that clears the day is the other real end of study mode."""
    guard, _ = create_guard(
        tmp_path,
        demo_mode=False,
        seeded=True,
        key_file=hmac_key,
        probe=probe_of("old-1"),
        poll_probe=probe_of("brand-new", "also-new", "old-1"),
    )
    set_arming(
        guard.lock,
        replace(arming(guard.lock), recovery=MagicMock(), detector=MagicMock()),
    )
    guard.open_problem(URL)
    assert restart.read_marker(DAY) is True

    guard.on_poll_result(guard.check())

    assert not guard.decision().locked
    assert not restart.marker_path().exists()


def _resumable(*, active: bool, raises: bool = False) -> MagicMock:
    """A guard whose ``enter_study`` leaves study ``active`` (or raises)."""
    guard = MagicMock()
    guard.session.return_value.active = active
    if raises:
        guard.enter_study.side_effect = RuntimeError("boom")
    return guard


def test_resuming_enters_study_and_never_takes_the_grab():
    """The restart arms without the grab; entering study is all it does."""
    guard = _resumable(active=True)

    assert restart.resume_study(guard) is True

    guard.enter_study.assert_called_once()
    assert guard.enter_study.call_args.args[0]() is True  # the no-op "browser"
    guard.lock.grab_input.assert_not_called()


def test_a_resume_that_cannot_stand_the_lock_down_arms_the_grab():
    """No study mode, no unguarded surface: fall back to the full lock."""
    guard = _resumable(active=False)

    assert restart.resume_study(guard) is False

    guard.lock.grab_input.assert_called_once()


def test_a_resume_that_raises_puts_the_lock_back(caplog: pytest.LogCaptureFixture):
    """Whatever ``enter_study`` does wrong, the lock ends up armed."""
    guard = _resumable(active=False, raises=True)

    with caplog.at_level(logging.WARNING):
        assert restart.resume_study(guard) is False

    guard.back_to_lock.assert_called_once()
    guard.lock.grab_input.assert_called_once()
    assert any(r.levelno >= logging.WARNING for r in caplog.records)


def test_arming_for_a_resume_takes_no_grab():
    """``grab=False`` arms the step-back watch alone; ``True`` is the full arm."""
    lock = MagicMock()

    restart.arm_input(lock, grab=True)
    lock.grab_input.assert_called_once()
    with patch.object(restart, "start_stepback") as stepback:
        restart.arm_input(lock, grab=False)

    lock.grab_input.assert_called_once()  # still just the first call
    stepback.assert_called_once_with(lock)


def test_the_adapter_starts_the_step_back_watch():
    """The adapter's one added private reach: ``LockWindow._stepback.start``."""
    started: list[int] = []
    lock = SimpleNamespace(_stepback=SimpleNamespace(start=lambda: started.append(1)))

    start_stepback(lock)

    assert started == [1]
