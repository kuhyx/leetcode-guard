"""Tests for the layered wait and the single-instance lock."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from gatelock import RANK_DIET_GUARD, RANK_SCREEN_LOCKER, RANK_WAKE_ALARM, Arbiter

from leetcode_guard import _instance
from leetcode_guard._constants import RANK_LEETCODE_GUARD
from leetcode_guard._queue import stronger_claims, wait_for_turn

if TYPE_CHECKING:
    from pathlib import Path


def make_arbiter(app: str, rank: int, runtime: Path) -> Arbiter:
    arbiter = Arbiter(app, rank, grab="global", disable_vt=True, runtime_dir=runtime)
    arbiter.publish()
    return arbiter


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.value += seconds


def test_an_empty_ladder_arms_immediately(tmp_path: Path):
    arbiter = make_arbiter("leetcode_guard", RANK_LEETCODE_GUARD, tmp_path)
    clock = FakeClock()

    result = wait_for_turn(arbiter, sleep=clock.sleep, now=clock.now)

    assert not result.queued
    assert not result.timed_out
    assert clock.slept == []
    arbiter.release()


def test_we_queue_behind_the_workout_lock_and_arm_when_it_finishes(
    tmp_path: Path, caplog
):
    """Your rule, exactly: the workout lock shows first, then this one -- and
    this one never exits just because that one is running."""
    workout = make_arbiter("screen_locker", RANK_SCREEN_LOCKER, tmp_path)
    ours = make_arbiter("leetcode_guard", RANK_LEETCODE_GUARD, tmp_path)
    clock = FakeClock()

    released = {"done": False}

    def sleep(seconds: float) -> None:
        clock.sleep(seconds)
        if not released["done"]:
            workout.release()
            released["done"] = True

    with caplog.at_level(logging.INFO):
        result = wait_for_turn(ours, sleep=sleep, now=clock.now)

    assert result.queued
    assert result.blocked_by == ("screen_locker",)
    assert not result.timed_out
    assert result.waited_seconds > 0
    ours.release()


def test_a_lower_ranked_locker_is_not_waited_for(tmp_path: Path):
    """diet_guard sits below us, so it queues behind us -- not the reverse."""
    diet = make_arbiter("diet_guard", RANK_DIET_GUARD, tmp_path)
    ours = make_arbiter("leetcode_guard", RANK_LEETCODE_GUARD, tmp_path)
    clock = FakeClock()

    result = wait_for_turn(ours, sleep=clock.sleep, now=clock.now)

    assert not result.queued
    diet.release()
    ours.release()


def test_every_higher_ranked_app_is_named_once(tmp_path: Path):
    alarm = make_arbiter("wake_alarm", RANK_WAKE_ALARM, tmp_path)
    workout = make_arbiter("screen_locker", RANK_SCREEN_LOCKER, tmp_path)
    ours = make_arbiter("leetcode_guard", RANK_LEETCODE_GUARD, tmp_path)
    clock = FakeClock()

    def sleep(seconds: float) -> None:
        clock.sleep(seconds)
        alarm.release()
        workout.release()

    result = wait_for_turn(ours, sleep=sleep, now=clock.now)

    assert set(result.blocked_by) == {"wake_alarm", "screen_locker"}
    ours.release()


def test_the_deadline_arms_anyway_rather_than_leaving_the_pc_unlocked(
    tmp_path: Path, caplog
):
    """The backstop must never mean "give up and let them through"."""
    workout = make_arbiter("screen_locker", RANK_SCREEN_LOCKER, tmp_path)
    ours = make_arbiter("leetcode_guard", RANK_LEETCODE_GUARD, tmp_path)
    clock = FakeClock()

    with caplog.at_level(logging.ERROR):
        result = wait_for_turn(
            ours, poll=10.0, deadline=30.0, sleep=clock.sleep, now=clock.now
        )

    assert result.timed_out
    assert result.blocked_by == ("screen_locker",)
    assert any(record.levelno == logging.ERROR for record in caplog.records)
    workout.release()
    ours.release()


def test_stronger_claims_ignores_our_own(tmp_path: Path):
    ours = make_arbiter("leetcode_guard", RANK_LEETCODE_GUARD, tmp_path)

    assert stronger_claims(ours) == ()
    ours.release()


def test_a_dead_holder_stops_blocking_us(tmp_path: Path):
    """Liveness is the kernel's flock, so a SIGKILLed locker is noticed on the
    next tick -- no heartbeats, no staleness heuristics."""
    workout = make_arbiter("screen_locker", RANK_SCREEN_LOCKER, tmp_path)
    ours = make_arbiter("leetcode_guard", RANK_LEETCODE_GUARD, tmp_path)

    assert len(stronger_claims(ours)) == 1
    workout.release()
    assert stronger_claims(ours) == ()
    ours.release()


# -- single instance -------------------------------------------------------


def test_the_first_run_takes_the_lock(tmp_path: Path):
    lock = _instance.acquire(tmp_path / "instance.lock")

    assert lock is not None
    lock.release()


def test_a_second_run_stands_down(tmp_path: Path, caplog):
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


def test_the_lock_is_retakeable_after_release(tmp_path: Path):
    path = tmp_path / "instance.lock"
    first = _instance.acquire(path)
    assert first is not None
    first.release()

    second = _instance.acquire(path)

    assert second is not None
    second.release()


def test_an_unopenable_path_reports_failure_rather_than_raising(tmp_path: Path, caplog):
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")

    with caplog.at_level(logging.ERROR):
        assert _instance.acquire(blocker / "instance.lock") is None


def test_releasing_twice_is_safe(tmp_path: Path):
    lock = _instance.acquire(tmp_path / "instance.lock")
    assert lock is not None

    lock.release()
    lock.release()


def test_the_lock_file_records_the_pid(tmp_path: Path):
    import os

    path = tmp_path / "instance.lock"
    lock = _instance.acquire(path)
    assert lock is not None

    assert path.read_text(encoding="utf-8") == str(os.getpid())
    lock.release()


def test_a_close_failure_is_reported_not_raised(tmp_path: Path, caplog):
    lock = _instance.acquire(tmp_path / "instance.lock")
    assert lock is not None

    class Broken:
        def close(self):
            message = "cannot close"
            raise OSError(message)

    lock.handle.close()
    lock.handle = Broken()

    with caplog.at_level(logging.WARNING):
        lock.release()

    assert any("could not close" in record.message for record in caplog.records)
