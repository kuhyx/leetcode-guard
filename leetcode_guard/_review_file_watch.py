"""Bring the poll forward when the tutor rewrites ``review_due.json``.

The lock re-reads the file on its 30 s poll. The tutor rewrites it (temp file +
rename) seconds after kuhy rates his last card, so without this the SOLVE rows
would wait up to 30 s for the result of the review he just finished.

One step per run of the poller's existing 20 ms watch loop, no timer, thread
or process of its own: at most once per second it ``stat``s the file and
compares ``(inode, mtime_ns, size)`` with the last one seen. A change (the file
appearing or disappearing too) answers "poll now"; the poller turns that into
its ordinary ``check_now``, which coalesces with a probe already in flight.
This module reads, verifies and repaints nothing: the poll that follows does,
through the one path it always uses.

Only while it can matter (the real lock on a SOLVE unit with a module to
review). A missing file or a failing ``stat`` is the signature "absent", never
an error; a failure other than "missing" is logged once per lock run. Anything
else that raises is caught here and logged once per run: the watch loop must
survive it.
"""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Final

from leetcode_guard import _tutor_signed
from leetcode_guard._review_due_rows import REVIEW_DUE

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)

WATCH_INTERVAL_S: Final = 1.0
"""Gap between two ``stat`` calls: 60 a minute while the lock idles on SOLVE."""

Signature = tuple[int, int, int] | None
"""``(st_ino, st_mtime_ns, st_size)``; ``None`` is "absent"."""


class DueFileWatch:
    """Calling it is one watch step; ``True`` means "bring the poll forward"."""

    def __init__(
        self,
        active: Callable[[], bool],
        *,
        clock: Callable[[], float] | None = None,
        stat: Callable[[Path], os.stat_result] | None = None,
    ) -> None:
        """Watch only while ``active()``; ``clock`` and ``stat`` are test seams.

        Both default to the real ones, looked up when used (never bound here).
        """
        self._active = active
        self._clock = clock
        self._stat = stat
        self._next_at = 0.0
        self._primed = False
        self._seen: Signature = None
        self._warned = False
        self._stat_warned = False

    def __call__(self) -> bool:
        """One step: never raises, so the Tk watch loop cannot be killed by it."""
        try:
            return self._step()
        except Exception:  # pylint: disable=broad-exception-caught
            if not self._warned:  # one line per lock run, with the traceback
                self._warned = True
                _logger.exception("the review file watch failed; will keep watching")
            return False

    def _step(self) -> bool:
        if not self._active():
            self._primed = False  # the poll that re-enables it reads the file fresh
            return False
        now = (time.monotonic if self._clock is None else self._clock)()
        if now < self._next_at:
            return False
        self._next_at = now + WATCH_INTERVAL_S
        signature = self._signature()
        changed = self._primed and signature != self._seen
        self._seen, self._primed = signature, True
        return changed

    def _signature(self) -> Signature:
        """The file's signature now; the dir is resolved at call time."""
        stat = os.stat if self._stat is None else self._stat
        try:
            info = stat(_tutor_signed.TUTOR_DIR / REVIEW_DUE)
        except OSError as exc:
            # A missing file is ordinary (the lock's own read says so, once). Any
            # other refusal is "absent" too, but worth one line per lock run.
            if not isinstance(exc, FileNotFoundError) and not self._stat_warned:
                self._stat_warned = True
                _logger.warning("review_due.json cannot be stat-ed: %s", exc)
            return None
        return (info.st_ino, info.st_mtime_ns, info.st_size)
