"""Writing the signed difficulty rows: pool cache first, then LeetCode.

Split from ``_difficulty`` for the 250-line cap. Everything that *writes* a row
lives here; the weight path (``load_weights``) never touches the unsigned pool
cache or the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard import _constants
from leetcode_guard._difficulty import difficulty_row, trusted_levels
from leetcode_guard._difficulty_negative import (
    is_backed_off,
    load_unresolved,
    save_unresolved,
)
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
    backed_off: int = 0
    """Slugs LeetCode answered unresolved less than a day ago; not asked again."""


def _fetch_level(post: PostFn, slug: str) -> tuple[str | None, bool]:
    """Ask LeetCode for one problem's difficulty: ``(level, unresolved)``.

    ``unresolved`` is True only when LeetCode *answered* without a usable
    difficulty (deleted problem, ``question: null``); a transport or GraphQL
    failure says nothing about the problem and is retried on the next call.
    """
    result = post(DIFFICULTY_QUERY, {"titleSlug": slug})
    if not result.ok:
        _logger.warning(
            "could not fetch the difficulty of %s: %s",
            slug,
            result.transport_error or "; ".join(result.errors) or "no data",
        )
        return None, False
    question = question_of(result.data)
    level = None if question is None else question.get("difficulty")
    if level not in DIFFICULTY_WEIGHTS:
        _logger.warning("no usable difficulty for %s: %r", slug, level)
        return None, True
    return str(level), False


def _pool_levels() -> dict[str, str]:
    """Difficulty per slug from the unsigned pool mirror. Write-side only."""
    pool = read_cache(_constants.POOL_CACHE_FILE)
    if pool is None:
        return {}
    return {problem.title_slug: problem.difficulty for problem in pool.problems}


@dataclass
class _Counts:
    """The per-call tallies :class:`ResolveResult` reports."""

    fetched: int = 0
    failed: int = 0
    deferred: int = 0
    backed_off: int = 0


@dataclass
class _Sweep:
    """One pass over the slugs that lack a trusted row."""

    post: PostFn
    now: datetime
    key_file: Path | None
    max_fetch: int
    pool: dict[str, str]
    marks: dict[str, float]
    rows: list[LedgerEntry] = field(default_factory=list)
    counts: _Counts = field(default_factory=_Counts)

    def take(self, slug: str) -> None:
        """Price one slug from the pool, else from LeetCode, else count it failed."""
        level, source = self.pool.get(slug), "pool"
        if level not in DIFFICULTY_WEIGHTS:
            if not self._may_fetch(slug):
                return
            level, source = self._fetch(slug), "graphql"
        if level is None:
            self.counts.failed += 1
            return
        self.marks.pop(slug, None)
        self.rows.append(
            difficulty_row(
                slug, level, now=self.now, key_file=self.key_file, source=source
            )
        )

    def _may_fetch(self, slug: str) -> bool:
        """Whether this call may ask LeetCode about ``slug``; counts the refusal."""
        if is_backed_off(self.marks, slug, now=self.now.timestamp()):
            self.counts.backed_off += 1
            return False
        if self.counts.fetched >= self.max_fetch:
            self.counts.deferred += 1
            return False
        return True

    def _fetch(self, slug: str) -> str | None:
        """Ask LeetCode, marking a slug it answered without a difficulty."""
        self.counts.fetched += 1
        level, unresolved = _fetch_level(self.post, slug)
        if unresolved:
            self.marks[slug] = self.now.timestamp()
        return level


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
    credit prices as Easy until a later call succeeds. A slug LeetCode answers
    without a usable difficulty is not asked again for a day (see
    :mod:`leetcode_guard._difficulty_negative`). Safe to repeat.
    """
    ledger = load_ledger(_constants.DIFFICULTY_FILE, key_file=key_file)
    have = trusted_levels(ledger)
    unique = list(dict.fromkeys(slugs))
    wanted = [slug for slug in unique if slug not in have]
    sweep = _Sweep(
        post=post,
        now=now,
        key_file=key_file,
        max_fetch=max_fetch,
        pool=_pool_levels() if wanted else {},
        marks=load_unresolved(_constants.DIFFICULTY_UNRESOLVED_FILE) if wanted else {},
    )
    marks_before = dict(sweep.marks)
    for slug in wanted:
        sweep.take(slug)
    for row in sweep.rows:
        # Replace, never append: a forged row under the same id must be overwritten.
        ledger.entries[row.entry_id] = row
    saved = bool(sweep.rows) and save_ledger(_constants.DIFFICULTY_FILE, ledger)
    if sweep.marks != marks_before:
        save_unresolved(_constants.DIFFICULTY_UNRESOLVED_FILE, sweep.marks)
    return ResolveResult(
        resolved=len(sweep.rows) if saved else 0,
        fetched=sweep.counts.fetched,
        already=len(unique) - len(wanted),
        failed=sweep.counts.failed
        + (0 if saved or not sweep.rows else len(sweep.rows)),
        deferred=sweep.counts.deferred,
        backed_off=sweep.counts.backed_off,
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
