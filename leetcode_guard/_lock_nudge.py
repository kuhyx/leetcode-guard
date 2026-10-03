"""Turn a browser nudge into a short burst of immediate solve checks.

The nudge only says "look now" (see ``_nudge_server``). One look is not enough:
LeetCode's recent-AC feed may lag the verdict the browser already showed, and a
single probe that lands before the feed updates would waste the nudge. So a
nudge schedules a few probes over four seconds and the burst ends at the first
one that mints a credit.

Every limit here is enforced in code because the doorbell is unauthenticated:
nudges inside the cooldown are dropped, a burst never overlaps another, and the
poller collapses pokes that arrive while a check is in flight.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Any, Final

from leetcode_guard._constants import POLL_DRAIN_MS
from leetcode_guard._nudge_server import NudgeServer

if TYPE_CHECKING:
    from leetcode_guard._poller import SolvePoller

_logger: Final = logging.getLogger(__name__)

NUDGE_BURST_RETRY_MS: Final = (1_000, 2_000, 4_000)
"""When to probe again after the immediate check a nudge starts. These cover a
feed that has not caught up with the verdict yet."""

NUDGE_COOLDOWN_SECONDS: Final = 5.0
"""Minimum gap between bursts. Longer than the burst itself, so at most four
extra requests per five seconds whatever is ringing the bell."""


class NudgeMixin:
    """Owns the doorbell, the bell flag and the burst schedule.

    Reads ``root`` and ``_poller`` from the host class.
    """

    root: Any
    _poller: SolvePoller[Any]
    _closed: bool

    def _start_nudges(self, port: int | None) -> None:
        """Open the doorbell on ``port`` and watch it on the Tk thread.

        ``None`` opens nothing: the lock still works, solves just wait for
        the regular poll.
        """
        self._bell = threading.Event()
        self._burst_jobs: list[str] = []
        self._last_burst = -NUDGE_COOLDOWN_SECONDS
        self._nudge_server: NudgeServer | None = None
        if port is None:
            return
        self._nudge_server = NudgeServer(self._bell.set, port=port)
        self._nudge_server.start()
        self.root.after(POLL_DRAIN_MS, self._watch_bell)

    def _stop_nudges(self) -> None:
        """Close the port and drop any pending burst. Idempotent."""
        if self._nudge_server is not None:
            self._nudge_server.stop()
        self._end_burst()

    def _watch_bell(self) -> None:
        """Start a burst when the bell rang and the cooldown has passed."""
        if self._closed:
            return
        if self._bell.is_set():
            self._bell.clear()
            now = time.monotonic()
            if now - self._last_burst >= NUDGE_COOLDOWN_SECONDS:
                self._last_burst = now
                _logger.info("browser nudge: checking LeetCode now")
                self._poller.check_now()
                self._burst_jobs = [
                    self.root.after(delay, self._poller.poke)
                    for delay in NUDGE_BURST_RETRY_MS
                ]
        self.root.after(POLL_DRAIN_MS, self._watch_bell)

    def _end_burst(self) -> None:
        """Cancel the rest of a burst: the credit it was waiting for landed."""
        for job in self._burst_jobs:
            self.root.after_cancel(job)
        self._burst_jobs.clear()
