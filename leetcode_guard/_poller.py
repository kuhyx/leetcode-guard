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
import threading
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

    def after_cancel(self, job: str) -> None:
        """Cancel a job ``after`` scheduled."""


class SubmitsWork(Protocol):
    """The only thing this module needs from an executor."""

    def submit(self, fn: Callable[[], _R]) -> Future[_R]:
        """Run ``fn`` off the calling thread."""

    def shutdown(self, *, wait: bool = ...) -> None:
        """Release the executor's resources."""


@dataclass(frozen=True)
class PollerSettings[R]:
    """What a :class:`SolvePoller` runs and how often.

    One record rather than five keyword arguments: the poller's constructor
    stays within the lint profile's argument limit, and a caller (or a test)
    can build the settings once and reuse them.

    Attributes:
        interval_ms: Gap between checks.
        work: The blocking call. Runs on the executor, never on Tk.
        on_result: Called on the Tk thread with whatever ``work`` returned.
        executor: Something with ``submit``. ``None`` means a single-worker
            thread pool the poller owns and shuts down; tests pass an inline
            one so ordering is deterministic and no threads are involved.
        drain_ms: How often to check whether the future has finished.
    """

    interval_ms: int
    work: Callable[[], R | None]
    on_result: Callable[[R | None], None]
    executor: SubmitsWork | None = None
    drain_ms: int = POLL_DRAIN_MS


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

    def __init__(self, root: AfterScheduler, settings: PollerSettings[R]) -> None:
        """Create the poller.

        Args:
            root: The Tk root, used only for ``after`` scheduling.
            settings: The work, its callback and the timing; see
                :class:`PollerSettings`.
        """
        self._root = root
        self._settings = settings
        self._executor: SubmitsWork = (
            settings.executor
            if settings.executor is not None
            else ThreadPoolExecutor(max_workers=1)
        )
        self.future: Future[R | None] | None = None
        self.stopped = False
        self._tick_job: str | None = None
        self._poked = threading.Event()
        self._in_flight_poked = False
        self.last_was_poke = False
        """Whether the result being delivered came from :meth:`poke`.

        Read by ``on_result``: an extra check asked for from outside must not
        count towards blind time, or a burst of forged pokes would buy the
        escape hatch in seconds."""
        self.state = PollState()

    @property
    def owns_executor(self) -> bool:
        """Whether this poller created the executor, and so must shut it down."""
        return self._settings.executor is None

    def start(self) -> None:
        """Kick off the first check immediately, and start watching for pokes."""
        self.stopped = False
        self.tick()
        self._root.after(self._settings.drain_ms, self._watch)

    def poke(self) -> None:
        """Ask for a check as soon as none is in flight.

        Safe from any thread -- it only sets an Event; the Tk thread notices it
        within ``drain_ms``. Pokes arriving while a check is in flight collapse
        into one, so they can never stack requests.
        """
        self._poked.set()

    def check_now(self) -> None:
        """Tk thread only: :meth:`poke` without waiting for the next watch."""
        self.poke()
        self._fire_poke()

    def _watch(self) -> None:
        """On the Tk thread: turn a pending poke into an immediate check."""
        if self.stopped:
            return
        self._fire_poke()
        self._root.after(self._settings.drain_ms, self._watch)

    def _fire_poke(self) -> None:
        """Start the poked check if the poller is idle between checks.

        A pending tick means idle. While a check is in flight the poke stays
        set and fires on the first watch after it lands.
        """
        if self.stopped or not self._poked.is_set() or self._tick_job is None:
            return
        self._poked.clear()
        self._root.after_cancel(self._tick_job)
        self._tick_job = None
        self.tick(poked=True)

    def stop(self) -> None:
        """Stop scheduling. Idempotent."""
        self.stopped = True
        if self.owns_executor:
            self._executor.shutdown(wait=False)

    def tick(self, *, poked: bool = False) -> None:
        """Submit a check, unless one is already in flight."""
        self._tick_job = None
        if self.stopped:
            return
        if self.future is None or self.future.done():
            self._in_flight_poked = poked
            self.future = self._executor.submit(self._guarded_work)
        self._root.after(self._settings.drain_ms, self.drain)

    def _guarded_work(self) -> R | None:
        """Run ``work``, converting a crash into a value.

        Returning ``None`` rather than propagating keeps the loop alive: an
        exception here would otherwise be swallowed by the future and the
        result callback would simply stop firing, leaving a permanently locked
        screen with no diagnosis.
        """
        try:
            return self._settings.work()
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.exception("the solve check raised; treating it as unverifiable")
            return None

    def drain(self) -> None:
        """On the Tk thread: deliver a finished result, then reschedule."""
        if self.stopped:
            return
        future = self.future
        if future is not None and future.done():
            self.future = None
            self.last_was_poke = self._in_flight_poked
            self._deliver(future)
            self._tick_job = self._root.after(self._settings.interval_ms, self.tick)
            return
        self._root.after(self._settings.drain_ms, self.drain)

    def _deliver(self, future: Future[R | None]) -> None:
        """Hand one result to the callback, never letting it kill the loop."""
        try:
            result = future.result()
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.exception("the solve check future failed")
            return
        try:
            self._settings.on_result(result)
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.exception("the poll result handler raised")
