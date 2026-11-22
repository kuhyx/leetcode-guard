"""The poller's watch hook: ``on_watch`` returning True brings the poll forward.

It reuses the poke path, so a request while a check is in flight coalesces
instead of queuing a second network probe.
"""

from __future__ import annotations

from leetcode_guard._poller import PollerSettings, SolvePoller
from leetcode_guard.tests.test_poller_poke import FakeRoot, ManualExecutor


def _poller(root: FakeRoot, executor: ManualExecutor, hook: list[bool]) -> SolvePoller:
    """A poller whose watch hook answers from ``hook`` (False when it runs dry)."""
    settings = PollerSettings(
        interval_ms=30_000,
        work=str,
        on_result=print,
        executor=executor,
        on_watch=lambda: hook.pop(0) if hook else False,
    )
    return SolvePoller(root, settings)


def test_a_true_hook_starts_the_check_at_once() -> None:
    """Idle between polls: the watch step submits one check."""
    root, executor = FakeRoot(), ManualExecutor()
    hook: list[bool] = []
    poller = _poller(root, executor, hook)
    poller.start()
    executor.finish_all()
    root.run("drain")
    assert not executor.pending

    hook.append(True)
    root.run("_watch")

    assert len(executor.pending) == 1


def test_a_false_hook_does_nothing() -> None:
    """No request: the pending tick stays pending."""
    root, executor = FakeRoot(), ManualExecutor()
    poller = _poller(root, executor, [])
    poller.start()
    executor.finish_all()
    root.run("drain")

    root.run("_watch")

    assert not executor.pending


def test_requests_during_a_check_in_flight_coalesce() -> None:
    """Three requests while one probe runs: one more probe, after it lands."""
    root, executor = FakeRoot(), ManualExecutor()
    hook = [True, True, True]
    poller = _poller(root, executor, hook)
    poller.start()
    assert len(executor.pending) == 1

    for _ in range(3):
        root.run("_watch")
    assert len(executor.pending) == 1  # nothing stacked on the probe in flight

    executor.finish_all()
    root.run("drain")
    hook.append(False)
    root.run("_watch")

    assert len(executor.pending) == 1  # the one coalesced request
    executor.finish_all()
    root.run("drain")
    root.run("_watch")
    assert not executor.pending
