"""Tests for the background solve poller.

The property that matters most is that the loop cannot die. A poller that stops
delivering results leaves a locked screen that can never notice the solve which
would release it -- and it fails silently, because a future swallows the
exception.
"""

from __future__ import annotations

from concurrent.futures import Future
from typing import Any

from leetcode_guard._poller import PollerSettings, PollState, SolvePoller


class InlineExecutor:
    """Runs work immediately, so tests are deterministic and thread-free."""

    def __init__(self) -> None:
        self.submissions = 0

    def submit(self, fn, *args, **kwargs) -> Future:
        """Run the work now and return its finished future."""
        self.submissions += 1
        future: Future = Future()
        future.set_result(fn(*args, **kwargs))
        return future

    def shutdown(self, *, wait: bool = True) -> None:
        """Nothing to release."""


class FixedExecutor:
    """Hands back one prepared future without running the work."""

    def __init__(self, future: Future) -> None:
        self.future = future

    def submit(self, _fn, *_args, **_kwargs) -> Future:
        """Return the prepared future."""
        return self.future

    def shutdown(self, *, wait: bool = True) -> None:
        """Nothing to release."""


class FakeRoot:
    """Records `after` calls and lets the test drive them by hand."""

    def __init__(self) -> None:
        self.scheduled: list[tuple[int, Any]] = []

    def after(self, delay: int, callback) -> None:
        """Record the callback instead of scheduling it."""
        self.scheduled.append((delay, callback))

    def run_next(self) -> None:
        """Run the oldest recorded callback."""
        _delay, callback = self.scheduled.pop(0)
        callback()


def build(root: FakeRoot, work, on_result, **kwargs) -> SolvePoller:
    """Build a poller over an inline executor."""
    return SolvePoller(
        root,
        PollerSettings(
            interval_ms=kwargs.pop("interval_ms", 1000),
            work=work,
            on_result=on_result,
            executor=InlineExecutor(),
            **kwargs,
        ),
    )


def test_a_result_reaches_the_callback():
    """A finished check hands its result to on_result."""
    root = FakeRoot()
    seen: list[str] = []
    poller = build(root, lambda: "solved", seen.append)

    poller.start()
    root.run_next()

    assert seen == ["solved"]


def test_the_loop_reschedules_after_delivering():
    """Delivering a result books the next tick."""
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
    """A raising on_result still leaves the next tick booked."""
    root = FakeRoot()

    def explode(_result):
        message = "handler boom"
        raise RuntimeError(message)

    poller = build(root, lambda: 1, explode)
    poller.start()
    root.run_next()

    assert root.scheduled


def test_stop_prevents_further_work():
    """After stop no further check runs."""
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
    """An unfinished check is drained again at drain_ms."""
    root = FakeRoot()
    executor = FixedExecutor(Future())  # never completes
    settings = PollerSettings(
        interval_ms=1000,
        work=lambda: 1,
        on_result=lambda _: None,
        executor=executor,
    )
    poller = SolvePoller(root, settings)
    poller.start()

    root.run_next()

    assert root.scheduled[0][0] == settings.drain_ms


def test_a_failed_future_is_reported_without_calling_the_handler():
    """A check whose future failed never reaches on_result."""
    root = FakeRoot()
    seen: list[Any] = []
    broken: Future = Future()
    broken.set_exception(RuntimeError("nope"))
    poller = SolvePoller(
        root,
        PollerSettings(
            interval_ms=1000,
            work=lambda: 1,
            on_result=seen.append,
            executor=FixedExecutor(broken),
        ),
    )

    poller.start()
    root.run_next()  # the drain delivers the failed future

    assert seen == []


def test_the_default_executor_is_created_and_shut_down():
    """Without an injected executor the poller owns its own."""
    root = FakeRoot()
    poller = SolvePoller(
        root,
        PollerSettings(interval_ms=1000, work=lambda: 1, on_result=lambda _: None),
    )

    poller.start()
    poller.stop()

    assert poller.owns_executor


def test_poll_state_counts_consecutive_failures_and_resets():
    """PollState counts unusable ticks in a row and resets on a usable one."""
    state = PollState()

    state.record(usable=False)
    state.record(usable=False)

    assert state.consecutive_unverifiable == 2
    assert state.ticks == 2

    state.record(usable=True)

    assert state.consecutive_unverifiable == 0
    assert state.ticks == 3
