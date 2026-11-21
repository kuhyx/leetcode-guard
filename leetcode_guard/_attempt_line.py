"""The one-minute harvester's display-only ``attempts:`` line.

Two jobs per run, both writing only ``attempts.json`` (never the ledger):

* **Theory snapshot.** "A flag is fixed at solve time": for each recent solve,
  store the theory state of its curriculum unit as it is *now*, once. The
  harvester runs every minute, so "now" is within a minute of the credit.
* **Failed submissions.** LeetCode's accepted-only feed never shows a Wrong
  Answer, so while a problem tab is being watched (a heartbeat under two minutes
  old) the recent-submission list is fetched and merged, every status. No fresh
  beat means no network call at all.

Called by ``_harvest_run.main`` after the harvest, never from inside it, and
fenced there: nothing here may stop a credit or change the exit code. Reads the
ledger only through ``load_ledger`` and never saves it. The solve is the
EARLIEST credit of a slug -- a re-solve of an old problem is not a new solve.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import TYPE_CHECKING, Final

from leetcode_guard._attempt_model import day_of, record_key
from leetcode_guard._attempt_queries import fetch_recent_submissions
from leetcode_guard._attempt_store import load, merge_submissions, snapshot_theory
from leetcode_guard._constants import LEDGER_FILE, POOL_CACHE_FILE
from leetcode_guard._curriculum import Theory
from leetcode_guard._ledger import CREDIT
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard._pool_cache import read_cache
from leetcode_guard._settings import build_client
from leetcode_guard._theory import load_blocks

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from leetcode_guard._attempt_model import AttemptRecord
    from leetcode_guard._attempt_queries import RecentSubmission
    from leetcode_guard._curriculum import Blocks
    from leetcode_guard._ledger import LedgerEntry

_logger: Final = logging.getLogger(__name__)

FRESH_BEAT_SECONDS: Final = 120
"""A beat younger than this means a problem tab was watched just now."""
SOLVE_WINDOW_SECONDS: Final = 2 * 86_400
"""How far back a solve may be and still get its snapshot."""
_CREDIT_PREFIX: Final = "ac:"


@dataclass(frozen=True)
class _Solve:
    """A credited accepted submission, as the ledger recorded it."""

    submission_id: str
    slug: str
    at: int


def _solve_of(entry: LedgerEntry) -> _Solve | None:
    """The solve a credit row records, or ``None`` when a field is off."""
    slug: object = entry.detail.get("title_slug")
    raw: object = entry.detail.get("submitted_at")
    if entry.kind != CREDIT or not entry.entry_id.startswith(_CREDIT_PREFIX):
        return None
    if not (isinstance(slug, str) and slug and isinstance(raw, str)):
        return None
    if not (raw.isascii() and raw.isdigit()):
        return None
    return _Solve(entry.entry_id.removeprefix(_CREDIT_PREFIX), slug, int(raw))


def _recent_solves(entries: list[LedgerEntry], since: float) -> list[_Solve]:
    """The earliest solve of each slug, kept when it is not older than ``since``."""
    earliest: dict[str, _Solve] = {}
    for entry in entries:
        solve = _solve_of(entry)
        best = None if solve is None else earliest.get(solve.slug)
        if solve is not None and (best is None or solve.at < best.at):
            earliest[solve.slug] = solve
    return [solve for solve in earliest.values() if solve.at >= since]


def _blocks_or_none() -> Blocks | None:
    """The curriculum blocks; ``None`` when absent or when the reader fails."""
    try:
        return load_blocks()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _logger.warning("theory unavailable for the snapshot: %s", type(exc).__name__)
        return None


def _theory_resolver() -> Callable[[str], str]:
    """Slug -> the theory value of its unit now, ``unknown`` when unresolvable.

    The same two calls stage 1 uses for ``Suggestion.theory``: the pool cache
    gives the problem (its tags), ``Blocks.theory_of`` gives the unit's state.
    """
    pool = read_cache(POOL_CACHE_FILE)
    problems = {} if pool is None else {p.title_slug: p for p in pool.problems}
    blocks = _blocks_or_none()

    def resolve(slug: str) -> str:
        problem = problems.get(slug)
        if blocks is None or problem is None:
            return Theory.UNKNOWN.value
        return blocks.theory_of(problem).value

    return resolve


def _unsnapped(solve: _Solve, records: dict[str, AttemptRecord]) -> bool:
    """Whether the solve's record still has no theory snapshot."""
    found = records.get(record_key(day_of(solve.at), solve.slug))
    return found is None or found.theory_at_solve is None


def _snapshot_solves(
    records: dict[str, AttemptRecord], now: float, key_file: Path | None
) -> int:
    """Snapshot every recent solve that has none yet; returns how many were set."""
    ledger = load_ledger(LEDGER_FILE, key_file=key_file)
    solves = _recent_solves(list(ledger.entries.values()), now - SOLVE_WINDOW_SECONDS)
    todo = [solve for solve in solves if _unsnapped(solve, records)]
    if not todo:
        return 0
    resolve = _theory_resolver()
    done = 0
    for solve in todo:
        # The record must exist first: snapshot_theory never creates one.
        merge_submissions(
            [(solve.submission_id, solve.slug, "Accepted", solve.at)], now=now
        )
        done += snapshot_theory(
            day_of(solve.at), solve.slug, resolve(solve.slug), now=now
        )
    return done


def _fetch_recent() -> list[RecentSubmission] | None:
    """Production fetch: the harvester's own client and username."""
    client = build_client()
    return fetch_recent_submissions(client.post, client.username)


def _count(number: int, noun: str) -> str:
    """``1 snapshot``, ``2 snapshots``."""
    return f"{number} {noun}" + ("" if number == 1 else "s")


def _merge_failures(
    records: dict[str, AttemptRecord],
    now: float,
    fetch: Callable[[], list[RecentSubmission] | None],
) -> str | None:
    """Fetch and merge every status while a tab is watched; ``None`` = no fetch."""
    newest = max(
        (beat.at for found in records.values() for beat in found.beats), default=None
    )
    if newest is None or now - newest >= FRESH_BEAT_SECONDS:
        return None
    rows = fetch()
    if rows is None:
        _logger.warning("recent submissions could not be checked; nothing merged")
        return "could not check"
    added = merge_submissions(
        [(row.submission_id, row.slug, row.status, row.at) for row in rows], now=now
    )
    return _count(added, "submission")


def attempts_line(
    *,
    clock: Callable[[], float] = time.time,
    fetch: Callable[[], list[RecentSubmission] | None] = _fetch_recent,
    key_file: Path | None = None,
) -> str:
    """Run both jobs and describe what happened, for the journal.

    Args:
        clock: Unix seconds; injected so tests never sleep.
        fetch: The ``recentSubmissionList`` call; injected so tests never touch
            the network. ``None`` means "could not check".
        key_file: The ledger's HMAC key override, for tests.

    Returns:
        ``idle``, or a comma list such as ``2 submissions, 1 snapshot`` or
        ``could not check``.
    """
    now = clock()
    records = load()
    fetched = _merge_failures(records, now, fetch)
    snapshots = _snapshot_solves(records, now, key_file)
    parts = [fetched] if fetched else []
    if snapshots:
        parts.append(_count(snapshots, "snapshot"))
    return ", ".join(parts) or "idle"
