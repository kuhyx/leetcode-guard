"""Check a shortlist against LeetCode itself before showing it.

Split out of ``_pool_resolve.py`` for the 250-line cap. Resolving a pool is
offline work over caches; verifying it is the one step that talks to the
network, and re-paging the whole pool is exactly what must not happen here.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard._live_solved import LiveSolved, check_solved

if TYPE_CHECKING:
    from leetcode_guard._leetcode import PostFn
    from leetcode_guard._problem import Problem

_logger: Final = logging.getLogger(__name__)


def verify_live(
    ranked: list[Problem],
    *,
    post: PostFn | None,
    limit: int,
) -> tuple[list[Problem], LiveSolved]:
    """Drop the displayed problems LeetCode says are already solved.

    Rank first, verify second, backfill from the next candidates: the ranking
    is what decides which handful is worth a request, so it has to come first.
    Any confirmed solve is removed and the gap is refilled from further down
    the list, repeating until ``limit`` problems have survived a live check or
    the candidates run out.

    Args:
        ranked: Candidates, best first, already filtered by stored knowledge.
        post: The network seam, or ``None`` to skip the live check entirely
            (``--status`` and the MCP server must never fetch).
        limit: How many verified problems are wanted.

    Returns:
        The surviving problems and the accumulated live evidence.
    """
    if post is None or not ranked:
        return ranked, LiveSolved()

    kept: list[Problem] = []
    solved: set[str] = set()
    checked = 0
    attempted = 0
    remaining = list(ranked)
    while remaining and len(kept) < limit:
        batch = remaining[: limit - len(kept)]
        remaining = remaining[len(batch) :]
        evidence = check_solved(post, [problem.title_slug for problem in batch])
        solved |= evidence.solved
        checked += evidence.checked
        attempted += evidence.attempted
        kept.extend(p for p in batch if p.title_slug not in evidence.solved)
        if not evidence.signed_in:
            # Nothing came back non-null, so every further request would be
            # just as blind. Stop paying for them and keep the rest as ranked.
            kept.extend(remaining)
            remaining = []
            break
    return (
        kept + remaining,
        LiveSolved(solved=frozenset(solved), checked=checked, attempted=attempted),
    )


def live_note(evidence: LiveSolved) -> str | None:
    """Say what the live check actually established, or nothing."""
    if evidence.attempted == 0:
        return None
    if not evidence.signed_in:
        return (
            "Could not reach LeetCode to check solved-state just now -- showing "
            "what the local ledger knows."
        )
    if evidence.solved:
        count = len(evidence.solved)
        plural = "" if count == 1 else "s"
        return (
            f"Checked with LeetCode just now: dropped {count} problem{plural} "
            "already solved."
        )
    return "Checked with LeetCode just now: none of these are solved yet."
