"""Writing the signed difficulty rows: pool cache first, then LeetCode.

Split from ``_difficulty`` for the 250-line cap. Everything that *writes* a row
lives here; the weight path (``load_weights``) never touches the unsigned pool
cache or the network.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard import _constants
from leetcode_guard._difficulty import difficulty_row, trusted_levels
from leetcode_guard._ledger_io import load_ledger, save_ledger
from leetcode_guard._pool_cache import read_cache
from leetcode_guard._progress import DIFFICULTY_WEIGHTS
from leetcode_guard._queries import question_of
from leetcode_guard._submissions import ProbeStatus

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime
    from pathlib import Path

    from leetcode_guard._ledger import LedgerEntry
    from leetcode_guard._leetcode import PostFn
    from leetcode_guard._submissions import SolveProbe

_logger: Final = logging.getLogger(__name__)

DEFAULT_MAX_FETCH: Final = 5
"""Network lookups per call. The one-minute harvester and the lock's poll loop
stay polite: the rest are picked up on a later tick (the shared client is also
throttled to one request per ``THROTTLE_MIN_INTERVAL_SECONDS``)."""

DIFFICULTY_QUERY: Final = """
query questionDifficulty($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    titleSlug
    difficulty
  }
}
"""
"""One public request per unknown problem; needs no login."""


@dataclass(frozen=True)
class ResolveResult:
    """What one :func:`resolve_difficulties` call did."""

    resolved: int = 0
    """Rows written (pool cache plus network)."""
    fetched: int = 0
    already: int = 0
    failed: int = 0
    deferred: int = 0
    """Slugs left for a later call because ``max_fetch`` was reached."""


def _fetch_level(post: PostFn, slug: str) -> str | None:
    """Ask LeetCode for one problem's difficulty; ``None`` (logged) on failure."""
    result = post(DIFFICULTY_QUERY, {"titleSlug": slug})
    if not result.ok:
        _logger.warning(
            "could not fetch the difficulty of %s: %s",
            slug,
            result.transport_error or "; ".join(result.errors) or "no data",
        )
        return None
    question = question_of(result.data)
    level = None if question is None else question.get("difficulty")
    if level not in DIFFICULTY_WEIGHTS:
        _logger.warning("no usable difficulty for %s: %r", slug, level)
        return None
    return str(level)


def _pool_levels() -> dict[str, str]:
    """Difficulty per slug from the unsigned pool mirror. Write-side only."""
    pool = read_cache(_constants.POOL_CACHE_FILE)
    if pool is None:
        return {}
    return {problem.title_slug: problem.difficulty for problem in pool.problems}


def resolve_difficulties(
    slugs: Iterable[str],
    *,
    post: PostFn,
    now: datetime,
    key_file: Path | None = None,
    max_fetch: int = DEFAULT_MAX_FETCH,
) -> ResolveResult:
    """Write signed difficulty rows for every slug that lacks a trusted one.

    The pool cache answers first (no request); the rest are asked of LeetCode,
    at most ``max_fetch`` per call. Failures are logged and leave no row, so the
    credit prices as Easy until a later call succeeds. Safe to repeat.
    """
    ledger = load_ledger(_constants.DIFFICULTY_FILE, key_file=key_file)
    have = trusted_levels(ledger)
    unique = list(dict.fromkeys(slugs))
    wanted = [slug for slug in unique if slug not in have]
    already = len(unique) - len(wanted)
    pool = _pool_levels() if wanted else {}
    rows: list[LedgerEntry] = []
    fetched = failed = deferred = 0
    for slug in wanted:
        level, source = pool.get(slug), "pool"
        if level not in DIFFICULTY_WEIGHTS:
            if fetched >= max_fetch:
                deferred += 1
                continue
            fetched += 1
            level, source = _fetch_level(post, slug), "graphql"
        if level is None:
            failed += 1
            continue
        rows.append(
            difficulty_row(slug, level, now=now, key_file=key_file, source=source)
        )
    for row in rows:
        # Replace, never append: a forged row under the same id must be overwritten.
        ledger.entries[row.entry_id] = row
    saved = bool(rows) and save_ledger(_constants.DIFFICULTY_FILE, ledger)
    return ResolveResult(
        resolved=len(rows) if saved else 0,
        fetched=fetched,
        already=already,
        failed=failed + (0 if saved or not rows else len(rows)),
        deferred=deferred,
    )


def resolve_probe(
    probe: SolveProbe,
    *,
    post: PostFn,
    now: datetime,
    key_file: Path | None = None,
) -> ResolveResult:
    """Price what a probe is about to credit, BEFORE the balance is decided.

    Otherwise a Medium solve on a 2-credit day would bank as 1 and neither
    settle nor unlock until some later run. An unusable probe resolves nothing.
    """
    if probe.status is not ProbeStatus.OK:
        return ResolveResult()
    return resolve_difficulties(
        [submission.title_slug for submission in probe.submissions],
        post=post,
        now=now,
        key_file=key_file,
    )
