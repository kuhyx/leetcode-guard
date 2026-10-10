"""Turn a browser nudge into a short burst of immediate solve checks.

The nudge only says "look now" (see ``_nudge_server``). One look is not enough:
LeetCode's recent-AC feed may lag the verdict the browser already showed, and a
single probe that lands before the feed updates would waste the nudge. So a
nudge schedules a few probes over four seconds and the burst ends at the first
one that mints a credit. The early steps are tight because the target is the
strip's count dropping within a second of the verdict: a feed lagging by even
50 ms would otherwise push the credit out to the first retry.

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
    from collections.abc import Callable

    from leetcode_guard._poller import SolvePoller

_logger: Final = logging.getLogger(__name__)

NUDGE_BURST_RETRY_MS: Final = (250, 500, 1_000, 2_000, 4_000)
"""When to probe again after the immediate check a nudge starts. These cover a
feed that has not caught up with the verdict yet. One probe is a LeetCode round
trip (~0.2 s), and pokes landing while one is in flight collapse, so the first
second runs back to back without ever overlapping."""

NUDGE_VERIFY_GRACE_MS: Final = 1_000
"""How long after the last retry the "verifying" note may stay up: room for
that probe's own round trip. Past it the note clears whatever happened, so a
forged ring cannot leave a claim on screen."""

NUDGE_COOLDOWN_SECONDS: Final = 5.0
"""Minimum gap between bursts. Longer than the burst itself, so at most six
extra requests per five seconds whatever is ringing the bell."""


class NudgeMixin:
    """Owns the doorbell, the bell flag and the burst schedule.

    Reads ``root``, ``_poller`` and ``_refresh_strip`` from the host class.
    """

    root: Any
    _poller: SolvePoller[Any]
    _closed: bool
    _refresh_strip: Callable[[], None]

    nudge_verifying: bool = False
    """A ring started a burst that has neither credited nor run out yet."""

    nudge_down: bool = False
    """The doorbell could not open, so solves wait for the regular poll."""

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
        self.nudge_down = not self._nudge_server.start()
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
                self._burst_jobs.append(
                    self.root.after(
                        NUDGE_BURST_RETRY_MS[-1] + NUDGE_VERIFY_GRACE_MS,
                        self._burst_ran_out,
                    )
                )
                self.nudge_verifying = True
                self._refresh_strip()
        self.root.after(POLL_DRAIN_MS, self._watch_bell)

    def _burst_ran_out(self) -> None:
        """No probe in the burst credited anything: drop the note."""
        self._burst_jobs.clear()
        self.nudge_verifying = False
        self._refresh_strip()

    def _end_burst(self) -> None:
        """Cancel the rest of a burst: the credit it was waiting for landed.

        Does not repaint: the caller is mid-repaint already.
        """
        for job in self._burst_jobs:
            self.root.after_cancel(job)
        self._burst_jobs.clear()
        self.nudge_verifying = False
