"""Decide where this run's suggestion list comes from.

Order: a fresh cache, else a live fetch, else a stale cache, else nothing. Each
step degrades rather than failing, and every degradation produces a sentence
the lock surface shows the user -- silently offering a worse list is how a tool
stops being trustworthy.

Runs **before** the window is built, never inside a surface builder. A network
call on the paint path would mean no window when the network is down, and no
window is itself the bypass.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Final, Literal

from leetcode_guard._constants import POOL_TTL_SECONDS, SUGGESTION_COUNT
from leetcode_guard._pool_cache import CachedPool, read_cache, write_cache
from leetcode_guard._pool_fetch import fetch_pool
from leetcode_guard._pool_verify import (
    live_note,
    verify_live,
)
from leetcode_guard._problem import Problem, rank_pool

if TYPE_CHECKING:
    from pathlib import Path

    from leetcode_guard._auth import AuthState
    from leetcode_guard._leetcode import PostFn

_logger: Final = logging.getLogger(__name__)


PoolSource = Literal["live", "cache", "stale-cache", "none"]

_SECONDS_PER_DAY: Final = 86_400

NO_SUGGESTIONS_NOTE: Final = (
    "No suggestions available -- pick any LeetCode problem you like. Any "
    "accepted submission counts, including premium problems."
)


@dataclass(frozen=True)
class SolvedKnowledge:
    """Everything known about which problems are already solved.

    The two sources are deliberately packaged together because neither is
    sufficient alone. LeetCode's own ``status`` is authoritative but goes dark
    the moment the session expires -- which is the normal state, since the JWT
    lasts about two weeks with no refresh flow, and the pool query is public,
    so a dead session yields a full list whose every ``status`` is ``null``
    rather than an error. The ledger keeps working through that, but only ever
    saw the last few submissions the recent-AC feed returns.
    """

    auth: AuthState
    slugs: frozenset[str] = frozenset()
    """Locally recorded solves. A lower bound, never the full solved set."""

    verify_limit: int = SUGGESTION_COUNT
    """How many of the ranked problems to confirm live, one request each.

    Bounded because this runs before the lock window exists. Re-checking all
    4019 would be 4019 requests on that path, against an endpoint that answers
    a rate limit with the same null payload as an expired session -- so being
    exhaustive is a way to manufacture the failure being checked for."""


@dataclass(frozen=True)
class PoolResolution:
    """The suggestion list plus an honest account of where it came from."""

    problems: tuple[Problem, ...]
    source: PoolSource
    notes: tuple[str, ...]

    @property
    def empty(self) -> bool:
        """Whether there is nothing to suggest."""
        return not self.problems


def resolve_pool(
    post: PostFn | None,
    cache_path: Path,
    *,
    now: float,
    solved: SolvedKnowledge,
    ttl: float = POOL_TTL_SECONDS,
) -> PoolResolution:
    """Produce the ranked suggestion list for this run.

    Args:
        post: The network seam, or ``None`` to force cache-only resolution
            (used by ``--status`` and by the MCP server, which must never
            trigger a live fetch).
        cache_path: Where the on-disk pool mirror lives.
        now: Unix seconds, injected so freshness is testable.
        solved: What is known about already-solved problems, from both
            sources. Its auth note is always included. Nothing here decides
            *whether* to filter -- solved problems always are, from whichever
            source has the answer.
        ttl: Cache lifetime in seconds.

    Returns:
        The resolution. Never raises.
    """
    slugs = solved.slugs
    limit = solved.verify_limit
    notes = [solved.auth.note]
    if slugs:
        notes.append(_ledger_note(len(slugs)))

    cached = read_cache(cache_path)
    if cached is not None and cached.is_fresh(now=now, ttl=ttl):
        return _resolved(
            cached.problems, "cache", notes, solved_slugs=slugs, live=(post, limit)
        )

    if post is not None:
        fetched = fetch_pool(post)
        if fetched.problems:
            if not fetched.complete:
                notes.append(f"Problem list may be incomplete: {fetched.reason}.")
            write_cache(
                cache_path,
                CachedPool(
                    problems=fetched.problems,
                    fetched_at=now,
                    complete=fetched.complete,
                ),
            )
            return _resolved(
                fetched.problems,
                "live",
                notes,
                solved_slugs=slugs,
                live=(post, limit),
            )
        notes.append(f"Could not refresh the problem list: {fetched.reason}.")

    if cached is not None:
        notes.append(_stale_note(cached, now=now))
        return _resolved(
            cached.problems,
            "stale-cache",
            notes,
            solved_slugs=slugs,
            live=(post, limit),
        )

    _logger.warning("no problem pool available: no live fetch and no cache")
    notes.append(NO_SUGGESTIONS_NOTE)
    return PoolResolution(problems=(), source="none", notes=tuple(notes))


def _stale_note(cached: CachedPool, *, now: float) -> str:
    """Explain how old the fallback list is, in days."""
    days = max(0, int(cached.age_seconds(now) // _SECONDS_PER_DAY))
    plural = "" if days == 1 else "s"
    return (
        f"Showing a cached problem list last refreshed {days} day{plural} ago "
        "(LeetCode is unreachable)."
    )


def _ledger_note(count: int) -> str:
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


def _resolved(
    problems: tuple[Problem, ...],
    source: PoolSource,
    notes: list[str],
    *,
    solved_slugs: frozenset[str],
    live: tuple[PostFn | None, int] = (None, SUGGESTION_COUNT),
) -> PoolResolution:
    """Rank and package a non-empty pool, verifying the top of it live."""
    post, limit = live
    ranked = rank_pool(problems, solved_slugs=solved_slugs)
    ranked, evidence = verify_live(ranked, post=post, limit=limit)
    note = live_note(evidence)
    if note is not None:
        notes.append(note)
    if not ranked:
        notes.append(NO_SUGGESTIONS_NOTE)
    return PoolResolution(problems=tuple(ranked), source=source, notes=tuple(notes))
