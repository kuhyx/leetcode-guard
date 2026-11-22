"""The sentences ``resolve_pool`` adds when it falls back or filters.

Split out of :mod:`leetcode_guard._pool_resolve` for the 250-line cap; no
decision lives here, only wording.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from leetcode_guard._pool_cache import CachedPool

SECONDS_PER_DAY: Final = 86_400


def stale_note(cached: CachedPool, *, now: float) -> str:
    """Explain how old the fallback list is, in days."""
    days = max(0, int(cached.age_seconds(now) // SECONDS_PER_DAY))
    plural = "" if days == 1 else "s"
    return (
        f"Showing a cached problem list last refreshed {days} day{plural} ago "
        "(LeetCode is unreachable)."
    )


def ledger_note(count: int) -> str:
    """Report the local filter without overstating what it knows.

    Deliberately "at least": the ledger only ever saw the handful of
    submissions the recent-AC feed returns, so it is a lower bound on what has
    been solved. Claiming more is the exact bug this filter exists to fix.
    """
    plural = "" if count == 1 else "s"
    return (
        f"Hiding at least {count} problem{plural} already solved on this "
        "device, from the local ledger."
    )


def refresh_failed_note(reason: str) -> str:
    """Say the refresh failed (or came back cut short) and why."""
    return f"Could not refresh the problem list: {reason}."
