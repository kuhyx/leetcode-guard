"""Run the solve check off the Tk thread.

A synchronous ``requests`` call inside a ``root.after`` callback would freeze a
globally-grabbed lock for the entire network timeout. To the user that is
indistinguishable from a hang, on a window they cannot escape. So the work runs
on an executor and the Tk thread only ever polls a future for completion.

The loop is also required never to die. An exception escaping the work function
is caught, logged with its traceback, and converted into an unverifiable
outcome -- because a dead poller means a lock that can never notice the solve
that would release it.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Final, Protocol, TypeVar

from leetcode_guard._constants import POLL_DRAIN_MS

if TYPE_CHECKING:
    from collections.abc import Callable

_logger: Final = logging.getLogger(__name__)

_R = TypeVar("_R")
"""What one check returns. The poller never inspects it -- generic rather than
``Any`` so the result type stays honest all the way to ``on_result``."""


class AfterScheduler(Protocol):
    """The only thing this module needs from a Tk root.

    A Protocol rather than ``tk.Misc`` so the tests can drive the loop with a
    plain recorder object, and so the lint profile's ban on bare ``Any``
    parameters is satisfied honestly rather than suppressed.
    """

    def after(self, ms: int, func: Callable[[], None]) -> str:
        """Schedule ``func`` to run on the Tk thread after ``ms``."""
        ...  # pragma: no cover


class SubmitsWork(Protocol):
    """The only thing this module needs from an executor."""

    def submit(self, fn: Callable[[], _R]) -> Future[_R]:
        """Run ``fn`` off the calling thread."""
        ...  # pragma: no cover

    def shutdown(self, *, wait: bool = ...) -> None:
        """Release the executor's resources."""
        ...  # pragma: no cover


@dataclass
class PollState:
    """How the check has been going.

    ``consecutive_unverifiable`` is what drives the failure policy: it resets
    to zero on any usable answer, so a single dropped packet never escalates.
    """

    ticks: int = 0
    consecutive_unverifiable: int = 0

    def record(self, *, usable: bool) -> None:
        """Fold one outcome into the running state."""
        self.ticks += 1
        if usable:
            self.consecutive_unverifiable = 0
        else:
            self.consecutive_unverifiable += 1


class SolvePoller[R]:
    """Drive a periodic background check from the Tk event loop."""

    def __init__(
        self,
        root: AfterScheduler,
        *,
        interval_ms: int,
        work: Callable[[], _R | None],
        on_result: Callable[[_R | None], None],
        executor: SubmitsWork | None = None,
        drain_ms: int = POLL_DRAIN_MS,
    ) -> None:
        """Create the poller.

        Args:
            root: The Tk root, used only for ``after`` scheduling.
            interval_ms: Gap between checks.
            work: The blocking call. Runs on the executor, never on Tk.
            on_result: Called on the Tk thread with whatever ``work`` returned.
            executor: Something with ``submit``. Defaults to a single-worker
                thread pool; tests pass an inline one so ordering is
                deterministic and no threads are involved.
            drain_ms: How often to check whether the future has finished.
        """
        self._root = root
        self._interval_ms = interval_ms
        self._work = work
        self._on_result = on_result
        self._executor = (
            executor if executor is not None else ThreadPoolExecutor(max_workers=1)
        )
        self._owns_executor = executor is None
        self._drain_ms = drain_ms
        self._future: Future[_R | None] | None = None
        self._stopped = False
        self.state = PollState()

    def start(self) -> None:
        """Kick off the first check immediately."""
        self._stopped = False
        self._tick()

    def stop(self) -> None:
        """Stop scheduling. Idempotent."""
        self._stopped = True
        if self._owns_executor:
            self._executor.shutdown(wait=False)

    def _tick(self) -> None:
        """Submit a check, unless one is already in flight."""
        if self._stopped:
            return
        if self._future is None or self._future.done():
            self._future = self._executor.submit(self._guarded_work)
        self._root.after(self._drain_ms, self._drain)

    def _guarded_work(self) -> _R | None:
        """Run ``work``, converting a crash into a value.

        Returning ``None`` rather than propagating keeps the loop alive: an
        exception here would otherwise be swallowed by the future and the
        result callback would simply stop firing, leaving a permanently locked
        screen with no diagnosis.
        """
        try:
            return self._work()
        except Exception:
            _logger.exception("the solve check raised; treating it as unverifiable")
            return None

    def _drain(self) -> None:
        """On the Tk thread: deliver a finished result, then reschedule."""
        if self._stopped:
            return
        future = self._future
        if future is not None and future.done():
            self._future = None
            self._deliver(future)
            self._root.after(self._interval_ms, self._tick)
            return
        self._root.after(self._drain_ms, self._drain)

    def _deliver(self, future: Future[_R | None]) -> None:
        """Hand one result to the callback, never letting it kill the loop."""
        try:
            result = future.result()
        except Exception:
            _logger.exception("the solve check future failed")
            return
        try:
            self._on_result(result)
        except Exception:
            _logger.exception("the poll result handler raised")
