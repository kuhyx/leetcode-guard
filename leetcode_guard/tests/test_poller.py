"""Tests for the background solve poller.

The property that matters most is that the loop cannot die. A poller that stops
delivering results leaves a locked screen that can never notice the solve which
would release it -- and it fails silently, because a future swallows the
exception.
"""

from __future__ import annotations

from concurrent.futures import Future
from typing import Any

from leetcode_guard._poller import PollState, SolvePoller


class InlineExecutor:
    """Runs work immediately, so tests are deterministic and thread-free."""

    def __init__(self) -> None:
        self.submissions = 0

    def submit(self, fn, *args, **kwargs) -> Future:
        self.submissions += 1
        future: Future = Future()
        future.set_result(fn(*args, **kwargs))
        return future

    def shutdown(self, *, wait: bool = True) -> None:
        pass


class FakeRoot:
    """Records `after` calls and lets the test drive them by hand."""

    def __init__(self) -> None:
        self.scheduled: list[tuple[int, Any]] = []

    def after(self, delay: int, callback) -> None:
        self.scheduled.append((delay, callback))

    def run_next(self) -> None:
        _delay, callback = self.scheduled.pop(0)
        callback()


def build(root: FakeRoot, work, on_result, **kwargs) -> SolvePoller:
    return SolvePoller(
        root,
        interval_ms=kwargs.pop("interval_ms", 1000),
        work=work,
        on_result=on_result,
        executor=InlineExecutor(),
        **kwargs,
    )


def test_a_result_reaches_the_callback():
    root = FakeRoot()
    seen: list[str] = []
    poller = build(root, lambda: "solved", seen.append)

    poller.start()
    root.run_next()

    assert seen == ["solved"]


def test_the_loop_reschedules_after_delivering():
    root = FakeRoot()
    poller = build(root, lambda: 1, lambda _: None)

    poller.start()
    root.run_next()

    assert root.scheduled


def test_a_crash_in_the_work_function_does_not_kill_the_loop():
    """A future swallows the exception, so without the guard the result
    callback would simply stop firing and the lock would hang forever."""
    root = FakeRoot()
    seen: list[Any] = []

    def explode():
        message = "boom"
        raise RuntimeError(message)

    poller = build(root, explode, seen.append)
    poller.start()
    root.run_next()

    assert seen == [None]
    assert root.scheduled


def test_a_crash_in_the_result_handler_does_not_kill_the_loop():
    root = FakeRoot()

    def explode(_result):
        message = "handler boom"
        raise RuntimeError(message)

    poller = build(root, lambda: 1, explode)
    poller.start()
    root.run_next()

    assert root.scheduled


def test_stop_prevents_further_work():
    root = FakeRoot()
    calls: list[int] = []
    poller = build(root, lambda: calls.append(1), lambda _: None)

    poller.start()
    poller.stop()
    while root.scheduled:
        root.run_next()

    assert len(calls) == 1


def test_start_after_stop_resumes():
    """`stop` is not terminal -- it un-schedules, and a later `start` revives
    the loop rather than leaving a lock that silently stopped checking."""
    root = FakeRoot()
    seen: list[Any] = []
    poller = build(root, lambda: 1, seen.append)

    poller.stop()
    poller.start()
    root.run_next()

    assert seen == [1]


def test_a_pending_future_is_drained_not_resubmitted():
    root = FakeRoot()
    executor = InlineExecutor()
    poller = SolvePoller(
        root,
        interval_ms=1000,
        work=lambda: 1,
        on_result=lambda _: None,
        executor=executor,
    )
    poller.start()
    poller._future = Future()  # never completes

    root.run_next()

    assert root.scheduled[0][0] == poller._drain_ms


def test_a_failed_future_is_reported_without_calling_the_handler():
    root = FakeRoot()
    seen: list[Any] = []
    poller = SolvePoller(
        root,
        interval_ms=1000,
        work=lambda: 1,
        on_result=seen.append,
        executor=InlineExecutor(),
    )
    broken: Future = Future()
    broken.set_exception(RuntimeError("nope"))

    poller._deliver(broken)

    assert seen == []


def test_the_default_executor_is_created_and_shut_down():
    root = FakeRoot()
    poller = SolvePoller(
        root, interval_ms=1000, work=lambda: 1, on_result=lambda _: None
    )

    poller.start()
    poller.stop()

    assert poller._owns_executor


def test_poll_state_counts_consecutive_failures_and_resets():
    state = PollState()

    state.record(usable=False)
    state.record(usable=False)

    assert state.consecutive_unverifiable == 2
    assert state.ticks == 2

    state.record(usable=True)

    assert state.consecutive_unverifiable == 0
    assert state.ticks == 3
