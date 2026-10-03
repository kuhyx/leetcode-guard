"""Tests for poking the poller: an immediate check on request.

The nudge path depends on two properties: a poke while idle replaces the
pending tick rather than adding a second loop, and a poke while a check is in
flight waits for it rather than stacking a request on top.
"""

from __future__ import annotations

from concurrent.futures import Future
from typing import Any

from leetcode_guard._poller import SolvePoller


class FakeRoot:
    """Records ``after`` jobs by id so a test can run or cancel them."""

    def __init__(self) -> None:
        self.jobs: dict[str, tuple[int, Any]] = {}
        self.cancelled: list[str] = []
        self._next = 0

    def after(self, delay: int, callback: Any) -> str:
        self._next += 1
        job = f"after#{self._next}"
        self.jobs[job] = (delay, callback)
        return job

    def after_cancel(self, job: str) -> None:
        self.cancelled.append(job)
        self.jobs.pop(job, None)

    def run(self, name: str) -> None:
        """Run the first pending job whose callback is named ``name``."""
        for job, (_delay, callback) in list(self.jobs.items()):
            if getattr(callback, "__name__", "") == name:
                del self.jobs[job]
                callback()
                return
        msg = f"no pending {name}"
        raise AssertionError(msg)


class ManualExecutor:
    """Futures the test resolves by hand, to hold a check in flight."""

    def __init__(self) -> None:
        self.pending: list[tuple[Future[Any], Any]] = []

    def submit(self, fn: Any) -> Future[Any]:
        future: Future[Any] = Future()
        self.pending.append((future, fn))
        return future

    def finish_all(self) -> None:
        for future, fn in self.pending:
            future.set_result(fn())
        self.pending.clear()

    def shutdown(self, *, wait: bool = True) -> None:
        pass


def _poller(root: FakeRoot, executor: ManualExecutor, seen: list[bool]) -> SolvePoller:
    poller: SolvePoller = SolvePoller(
        root,
        interval_ms=30_000,
        work=lambda: "probe",
        on_result=lambda _r: None,
        executor=executor,
    )
    poller._on_result = lambda _r: seen.append(poller.last_was_poke)
    return poller


def _settle(root: FakeRoot, executor: ManualExecutor) -> None:
    """Finish the startup check, leaving the poller idle with a tick pending."""
    executor.finish_all()
    root.run("_drain")


def test_a_poke_while_idle_replaces_the_pending_tick() -> None:
    root, executor, seen = FakeRoot(), ManualExecutor(), []
    poller = _poller(root, executor, seen)
    poller.start()
    _settle(root, executor)
    tick_job = next(j for j, (d, _c) in root.jobs.items() if d == 30_000)

    poller.poke()
    root.run("_watch")

    assert root.cancelled == [tick_job]
    assert len(executor.pending) == 1
    _settle(root, executor)
    assert seen == [False, True]


def test_a_poke_while_a_check_is_in_flight_waits_for_it() -> None:
    root, executor, seen = FakeRoot(), ManualExecutor(), []
    poller = _poller(root, executor, seen)
    poller.start()

    poller.poke()
    root.run("_watch")

    assert len(executor.pending) == 1, "a second request was stacked"
    _settle(root, executor)
    root.run("_watch")
    assert len(executor.pending) == 1
    _settle(root, executor)
    assert seen == [False, True]


def test_many_pokes_collapse_into_one_check() -> None:
    root, executor, seen = FakeRoot(), ManualExecutor(), []
    poller = _poller(root, executor, seen)
    poller.start()
    _settle(root, executor)

    for _ in range(5):
        poller.poke()
    root.run("_watch")
    root.run("_watch")

    assert len(executor.pending) == 1


def test_check_now_skips_the_wait_for_the_next_watch() -> None:
    root, executor, seen = FakeRoot(), ManualExecutor(), []
    poller = _poller(root, executor, seen)
    poller.start()
    _settle(root, executor)

    poller.check_now()

    assert len(executor.pending) == 1


def test_a_stopped_poller_ignores_pokes_and_stops_watching() -> None:
    root, executor, seen = FakeRoot(), ManualExecutor(), []
    poller = _poller(root, executor, seen)
    poller.start()
    _settle(root, executor)
    poller.stop()

    poller.check_now()
    root.run("_watch")

    assert executor.pending == []
    assert not any(c.__name__ == "_watch" for _d, c in root.jobs.values())
