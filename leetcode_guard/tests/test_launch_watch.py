"""The tutor launcher's exit is watched on the Tk loop (``_launch_watch``).

A launcher that starts and then exits non-zero opened no window; before
2026-11-22 the lock never saw it and stayed in study mode with nothing on
screen. These pin the poll itself; ``test_lock_learn_exit`` pins what the
lock does with a failure, ``scripts/verify_review_first`` the real thing.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from leetcode_guard._launch_watch import WATCH_MS, watch_exit

if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest


class _Proc:
    """A process whose ``poll`` answers from a script, then repeats the last."""

    def __init__(self, *answers: object) -> None:
        self.answers = list(answers)

    def poll(self) -> object:
        """The next scripted answer; an exception is raised."""
        answer = self.answers[0]
        if len(self.answers) > 1:
            self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class _Loop:
    """``root.after``, run by hand: each call queues one callback."""

    def __init__(self) -> None:
        self.queued: list[tuple[int, Callable[[], None]]] = []

    def after(self, ms: int, fn: Callable[[], None]) -> None:
        """Queue ``fn``, as ``root.after`` would."""
        self.queued.append((ms, fn))

    def run(self) -> int:
        """Run queued callbacks until none is left; how many ran."""
        ran = 0
        while self.queued:
            _, fn = self.queued.pop(0)
            fn()
            ran += 1
        return ran


def test_a_handle_without_poll_is_not_watched():
    """A test's stand-in (or ``object()``) is not a process: nothing scheduled."""
    loop = _Loop()

    assert not watch_exit(loop.after, object(), lambda _s: None)
    assert loop.queued == []


def test_a_launcher_that_exits_zero_ends_the_watch_quietly():
    """Still running, still running, exit 0: three polls, no failure."""
    loop, failed = _Loop(), []

    assert watch_exit(loop.after, _Proc(None, None, 0), failed.append)

    assert loop.run() == 3
    assert failed == []
    assert loop.queued == []


def test_a_non_zero_exit_is_reported_once_with_its_status():
    """The status is what goes on the lock; polling stops after it."""
    loop, failed = _Loop(), []

    watch_exit(loop.after, _Proc(None, 1), failed.append)

    assert loop.run() == 2
    assert failed == [1]


def test_the_poll_runs_every_watch_interval():
    """One ``after`` per poll, at ``WATCH_MS``: no thread, no deadline."""
    loop = _Loop()

    watch_exit(loop.after, _Proc(None), lambda _s: None)
    for _ in range(5):
        _, fn = loop.queued.pop(0)
        fn()

    assert [ms for ms, _ in loop.queued] == [WATCH_MS]


def test_a_poll_that_raises_stops_the_watch_and_is_logged(
    caplog: pytest.LogCaptureFixture,
):
    """Never into the Tk loop: one logged line, no failure, no reschedule."""
    loop, failed = _Loop(), []

    watch_exit(loop.after, _Proc(OSError("gone")), failed.append)
    with caplog.at_level(logging.WARNING):
        assert loop.run() == 1

    assert failed == []
    assert "could not poll the tutor launcher" in caplog.text


def test_a_status_that_is_not_an_int_is_not_a_failure():
    """A MagicMock's ``poll`` answers a MagicMock: unknown, never a relock."""
    loop, failed = _Loop(), []

    watch_exit(loop.after, MagicMock(), failed.append)

    assert loop.run() == 1
    assert failed == []
