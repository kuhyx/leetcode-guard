"""Defer the gate while the phone's morning session is earning the carrot.

The reader itself is ``gatelock.morning_session``, shared with screen-locker
and book-guard; this module only binds leetcode-guard's path and retry budget
(both redirected by the test suite) and words the reason. The policy lives in
wake-alarm: the only decision anywhere is *signature ok, dated today,
now < exempt_until*. Missing, stale, failed or tampered all mean "no deferral".

A run deferral, not ledger state: nothing here is written, so ``decide``
stays pure and a deleted file cannot mint an unlocked day. The arming run
waits for a mid-morning boot's catch-up, bounded; ``--check`` and ``--status``
never do.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from gatelock.morning_session import (
    MORNING_RETRY_SECONDS as _SHARED_RETRY_SECONDS,
)
from gatelock.morning_session import (
    morning_skip,
)

from leetcode_guard._constants import MORNING_SESSION_FILE

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

MORNING_RETRY_SECONDS: float = _SHARED_RETRY_SECONDS


def defer_for_morning_session(
    now: datetime,
    *,
    wait: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> str | None:
    """The reason to skip this arming run, or None to gate as usual."""
    skip = morning_skip(
        MORNING_SESSION_FILE,
        now,
        wait=wait,
        retry_seconds=MORNING_RETRY_SECONDS,
        sleep=sleep,
    )
    if skip is None:
        return None
    return f"morning session {skip.outcome}, no gate until {skip.exempt_until:%H:%M}"
