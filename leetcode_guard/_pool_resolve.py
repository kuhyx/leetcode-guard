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

from leetcode_guard._constants import POOL_TTL_SECONDS
from leetcode_guard._pool_cache import CachedPool, read_cache, write_cache
from leetcode_guard._pool_fetch import fetch_pool
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
    auth: AuthState,
    ttl: float = POOL_TTL_SECONDS,
) -> PoolResolution:
    """Produce the ranked suggestion list for this run.

    Args:
        post: The network seam, or ``None`` to force cache-only resolution
            (used by ``--status`` and by the MCP server, which must never
            trigger a live fetch).
        cache_path: Where the on-disk pool mirror lives.
        now: Unix seconds, injected so freshness is testable.
        auth: Whether already-solved problems can be filtered out. Its note is
            always included, so an unfiltered list always says it is one.
        ttl: Cache lifetime in seconds.

    Returns:
        The resolution. Never raises.
    """
    exclude_solved = auth.present
    notes = [auth.note]

    cached = read_cache(cache_path)
    if cached is not None and cached.is_fresh(now=now, ttl=ttl):
        return _resolved(cached.problems, "cache", notes, exclude_solved=exclude_solved)

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
                fetched.problems, "live", notes, exclude_solved=exclude_solved
            )
        notes.append(f"Could not refresh the problem list: {fetched.reason}.")

    if cached is not None:
        notes.append(_stale_note(cached, now=now))
        return _resolved(
            cached.problems, "stale-cache", notes, exclude_solved=exclude_solved
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


def _resolved(
    problems: tuple[Problem, ...],
    source: PoolSource,
    notes: list[str],
    *,
    exclude_solved: bool,
) -> PoolResolution:
    """Rank and package a non-empty pool."""
    ranked = rank_pool(problems, exclude_solved=exclude_solved)
    if not ranked:
        notes.append(NO_SUGGESTIONS_NOTE)
    return PoolResolution(problems=tuple(ranked), source=source, notes=tuple(notes))
