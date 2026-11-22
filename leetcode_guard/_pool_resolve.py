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
from typing import TYPE_CHECKING, Final, Literal, TypeGuard

from leetcode_guard._constants import POOL_TTL_SECONDS, SUGGESTION_COUNT
from leetcode_guard._pool_cache import CachedPool, read_cache, write_cache
from leetcode_guard._pool_fetch import fetch_pool
from leetcode_guard._pool_notes import ledger_note, stale_note
from leetcode_guard._pool_verify import (
    live_note,
    verify_live,
)
from leetcode_guard._problem import Problem, rank_pool
from leetcode_guard._theory import load_blocks
from leetcode_guard._unit_rank import focus_key

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from leetcode_guard._auth import AuthState
    from leetcode_guard._curriculum import Blocks
    from leetcode_guard._leetcode import PostFn

_logger: Final = logging.getLogger(__name__)


PoolSource = Literal["live", "cache", "stale-cache", "none"]

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

    key_file: Path | None = None
    """The HMAC key the signed theory phase is verified with; ``None`` = the
    shared key. It decides which unit's Easy problems lead (``_unit_rank``)."""


@dataclass(frozen=True)
class PoolResolution:
    """The suggestion list plus an honest account of where it came from."""

    problems: tuple[Problem, ...]
    source: PoolSource
    notes: tuple[str, ...]
    blocks: Blocks | None = None
    """The curriculum order the list was ranked by; ``None`` = acceptance order."""

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
    notes = [solved.auth.note]
    if solved.slugs:
        notes.append(ledger_note(len(solved.slugs)))

    cached = read_cache(cache_path, key_file=solved.key_file)
    can_fetch = post is not None
    if cached is not None and cached.is_current(
        now=now, ttl=ttl, refreshable=can_fetch
    ):
        return _resolved(cached.problems, "cache", notes, solved=solved, post=post)

    if post is not None:
        fetched = fetch_pool(post)
        if fetched.problems:
            if not fetched.complete and _is_good(cached):
                return _kept(cached, fetched.reason, notes, solved=solved, post=post)
            if not fetched.complete:
                notes.append(f"Problem list may be incomplete: {fetched.reason}.")
            write_cache(
                cache_path,
                CachedPool(
                    problems=fetched.problems,
                    fetched_at=now,
                    complete=fetched.complete,
                ),
                key_file=solved.key_file,
            )
            return _resolved(
                fetched.problems,
                "live",
                notes,
                solved=solved,
                post=post,
            )
        notes.append(f"Could not refresh the problem list: {fetched.reason}.")

    if cached is not None:
        notes.append(stale_note(cached, now=now))
        return _resolved(
            cached.problems,
            "stale-cache",
            notes,
            solved=solved,
            post=post,
        )

    _logger.warning("no problem pool available: no live fetch and no cache")
    notes.append(NO_SUGGESTIONS_NOTE)
    return PoolResolution(problems=(), source="none", notes=tuple(notes))


def _is_good(cached: CachedPool | None) -> TypeGuard[CachedPool]:
    """Whether the cache is one the theory phase can decide on."""
    return cached is not None and cached.verified and cached.complete


def _kept(
    cached: CachedPool,
    reason: str,
    notes: list[str],
    *,
    solved: SolvedKnowledge,
    post: PostFn | None,
) -> PoolResolution:
    """Answer from a good cache after a cut-short refresh, writing nothing.

    Overwriting it with the partial pool would fail the theory phase closed
    (it needs a verified, complete pool) until a later fetch works. The file
    keeps its old stamp, so it stays stale and the next refresher run retries.
    """
    _logger.warning(
        "pool refresh incomplete (%s): kept the last complete problem list", reason
    )
    notes.append(
        f"Problem list refresh was incomplete: {reason}. "
        "Showing the last complete list."
    )
    return _resolved(cached.problems, "stale-cache", notes, solved=solved, post=post)


def _ordering(
    problems: tuple[Problem, ...], solved: SolvedKnowledge
) -> tuple[Blocks | None, Callable[[Problem], tuple[int, ...]] | None]:
    """The curriculum blocks and the rank key, or ``(None, None)`` on any bug.

    The last-resort fence of a display-only read: ``resolve_pool`` runs with
    the instance lock held and before any window opens, so whatever the tutor
    reader or the unit focus does wrong must cost the ordering, never the
    lock. ``Exception`` only: ``KeyboardInterrupt`` and ``SystemExit`` still
    stop the process.
    """
    try:
        blocks = load_blocks()
        if blocks is None:
            return None, None
        key = focus_key(blocks, problems, solved.slugs, key_file=solved.key_file)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _logger.warning(
            "theory order unavailable, using acceptance order: %s",
            type(exc).__name__,
            exc_info=True,
        )
        return None, None
    return blocks, key


def _resolved(
    problems: tuple[Problem, ...],
    source: PoolSource,
    notes: list[str],
    *,
    solved: SolvedKnowledge,
    post: PostFn | None,
) -> PoolResolution:
    """Rank and package a non-empty pool, verifying the top of it live."""
    blocks, key = _ordering(problems, solved)
    ranked = rank_pool(problems, solved_slugs=solved.slugs, block=key)
    ranked, evidence = verify_live(ranked, post=post, limit=solved.verify_limit)
    note = live_note(evidence)
    if note is not None:
        notes.append(note)
    if not ranked:
        notes.append(NO_SUGGESTIONS_NOTE)
    return PoolResolution(
        problems=tuple(ranked), source=source, notes=tuple(notes), blocks=blocks
    )
