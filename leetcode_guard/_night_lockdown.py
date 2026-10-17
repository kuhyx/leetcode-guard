"""Do not re-arm the gate after tonight's evening night-lockdown.

The predicate itself is ``gatelock.night_lockdown``, shared with screen-locker
and book-guard (diet-guard deliberately does not opt in); this module only
binds leetcode-guard's path (redirected by the test suite) and words the
reason. Once tonight's lockdown has fired, a late credit can lift it, and
re-locking behind the LeetCode gate the same evening would make a finished
solve impossible to submit. Only an EVENING lock counts (local date today,
>= 12:00); the 04:01 morning re-lock does not.

A run deferral, never ledger state, exactly like the morning carrot: nothing
is written, so ``decide`` stays pure. Missing or garbage stamp means "no
deferral" and the gate arms as before.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gatelock.night_lockdown import evening_lockdown_today

from leetcode_guard._constants import NIGHT_LOCKDOWN_STAMP

if TYPE_CHECKING:
    from datetime import datetime


def defer_for_evening_lockdown(now: datetime) -> str | None:
    """The reason to skip this arming run, or None to gate as usual."""
    locked_at = evening_lockdown_today(NIGHT_LOCKDOWN_STAMP, now)
    if locked_at is None:
        return None
    return (
        f"night lockdown already locked tonight at {locked_at:%H:%M}; "
        "the gate does not re-arm after it"
    )
