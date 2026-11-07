"""Take an armed lock down when the morning carrot lands after it armed.

Incident 2026-11-07: the gate armed at 07:49:14 because today's signed
``morning_session.json`` (wake-alarm) had not reached the PC yet; it landed at
07:50:00 and the session later completed, exempt until 11:00. ``cmd_lock``
reads the file once, before arming, and an armed lock never looked again.

While the lock is up this re-reads it every 15 s, only between 05:00 and 11:00
local, through the same reader the arming run uses (``wait=False``: a poll
never sleeps on the Tk thread). A reason means the carrot is signed and ahead,
and the lock goes through the stand-down a verified solve uses (``_release``:
study mode ended first, then gatelock's ``close``, which stops RecoveryLoop
*before* the X grab is let go -- the other order leaves a focused window that
swallows every keystroke).

A deferral, not a solve: no ledger row is written, so ``rm ledger.json`` still
cannot mint an unlocked day. The reader's failure modes stay fail-closed:
missing, stale, unsigned or crashing all mean "keep the lock".
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final

from leetcode_guard._morning_session import defer_for_morning_session

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from leetcode_guard._lock_deps import GuardDeps
    from leetcode_guard._submissions import SolveProbe

_logger: Final = logging.getLogger(__name__)

CARROT_POLL_MS: Final = 15_000
"""Gap between checks. Short enough that a late file frees the user within a
poll, long enough that the signed-file read is noise."""

_WINDOW_START_HOUR: Final = 5
_WINDOW_END_HOUR: Final = 11
"""The carrot can only exist 05:00-11:00 (wake-alarm owns the exact cutoffs and
the reader enforces them); outside that this does not even open the file."""


def in_carrot_window(now: datetime) -> bool:
    """Whether ``now`` (local) falls in the hours a carrot can be earned."""
    return _WINDOW_START_HOUR <= now.hour < _WINDOW_END_HOUR


class CarrotMixin:
    """The late carrot check, mixed into the lock.

    Reads ``_deps``, ``_closed``, ``_demo``, ``_last_probe`` and ``root`` from
    the host class and calls its ``_release`` and ``_say``; declared rather
    than assumed, as the other mixins do.
    """

    _deps: GuardDeps
    _closed: bool
    _demo: bool
    _last_probe: SolveProbe
    root: Any
    _say: Callable[[str], None]
    _release: Callable[[SolveProbe], None]
    _carrot_job: str | None = None

    def _start_carrot_watch(self) -> None:
        """Begin polling, unless this is the demo (it never reads live state)."""
        if self._demo:
            return
        self._carrot_job = self.root.after(CARROT_POLL_MS, self._carrot_tick)

    def _stop_carrot_watch(self) -> None:
        """Cancel the pending check. Idempotent."""
        job, self._carrot_job = self._carrot_job, None
        if job is not None:
            self.root.after_cancel(job)

    def _carrot_tick(self) -> None:
        """One check; reschedules itself unless the lock is going away."""
        self._carrot_job = None
        if self._closed:
            return
        # Rescheduled first so a crash below can never end the watch.
        self._carrot_job = self.root.after(CARROT_POLL_MS, self._carrot_tick)
        now = self._deps.moment()
        if not in_carrot_window(now):
            return
        try:
            why = defer_for_morning_session(now, wait=False)
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.exception(
                "could not read the morning session; the lock stays up and "
                "this check retries in %d s",
                CARROT_POLL_MS // 1000,
            )
            return
        if why is None:
            return
        _logger.warning("standing the armed lock down: %s", why)
        self._stop_carrot_watch()
        self._release(self._last_probe)
        self._say(why)
