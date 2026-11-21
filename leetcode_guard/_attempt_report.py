"""The flagged-solve report: what ``--flagged`` prints and ``get_flagged`` returns.

Display-only and read-only. It reads the ledger (through ``load_ledger``) and
``attempts.json`` (through ``_attempt_store.load``) and writes nothing; no
deciding module may import it (``test_display_only_imports``). The definitions
live in :mod:`leetcode_guard._attempts`.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from leetcode_guard import _attempt_store, _constants
from leetcode_guard._attempt_model import day_of
from leetcode_guard._attempts import (
    FAST_SECONDS,
    FLAG_SECONDS,
    WINDOW_DAYS,
    Credit,
    Solve,
    credits_of,
    first_credits,
    measure,
)
from leetcode_guard._ledger_io import load_ledger

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from collections.abc import Set as AbstractSet

    from leetcode_guard._attempt_model import AttemptRecord


def _iso(stamp: int) -> str:
    """A unix time as a local ISO timestamp."""
    return datetime.fromtimestamp(stamp, tz=UTC).astimezone().isoformat()


def _row(found: Solve) -> dict[str, Any]:
    """One solve as report data; ``measured`` is implied by the list it is in."""
    row = asdict(found)
    del row["measured"]
    row["accepted_at"] = _iso(found.accepted_at)
    row["day"] = day_of(found.accepted_at)
    return row


def _newest_first(solves: Iterable[Solve]) -> list[Solve]:
    return sorted(solves, key=lambda found: (-found.accepted_at, found.slug))


def build_report(
    earned: Iterable[Credit],
    records: Mapping[str, AttemptRecord],
    *,
    now: datetime,
    cleared: AbstractSet[str] = frozenset(),
) -> dict[str, Any]:
    """Measure every solve and assemble the report.

    Args:
        earned: Every credit of the ledger; repeats of a slug are dropped.
        records: ``attempts.json``'s records, as ``_attempt_store.load`` gives.
        now: The report's clock; the 28-day window ends here.
        cleared: Slugs already reviewed, never flagged.

    Returns:
        JSON-serialisable data: the flagged solves of the whole retention, the
        measured and unknown solves of the last 28 days, and the share of
        measured ones under 10 minutes (``None``, never 0, with no data).
    """
    history: dict[str, list[AttemptRecord]] = {}
    for found in records.values():
        history.setdefault(found.slug, []).append(found)
    solves = [
        measure(credit, history.get(credit.slug, []), cleared=cleared)
        for credit in first_credits(earned)
    ]
    floor = (now - timedelta(days=WINDOW_DAYS)).timestamp()
    recent = _newest_first(s for s in solves if s.accepted_at >= floor)
    measured = [s for s in recent if s.measured]
    fast = sum(s.active_seconds < FAST_SECONDS for s in measured)
    return {
        "generated_at": now.astimezone().isoformat(),
        "threshold_seconds": FLAG_SECONDS,
        "window_days": WINDOW_DAYS,
        "flagged": [_row(s) for s in _newest_first(s for s in solves if s.flagged)],
        "measured": [_row(s) for s in measured],
        "unknown": [
            {"slug": s.slug, "accepted_at": _iso(s.accepted_at)}
            for s in recent
            if not s.measured
        ],
        "under_10_min_share": fast / len(measured) if measured else None,
    }


def load_report(
    *, now: datetime | None = None, cleared: AbstractSet[str] = frozenset()
) -> dict[str, Any]:
    """The report over the configured ledger and ``attempts.json``."""
    earned: list[Credit] = credits_of(load_ledger(_constants.LEDGER_FILE))
    return build_report(
        earned,
        _attempt_store.load(),
        now=datetime.now(tz=UTC) if now is None else now,
        cleared=cleared,
    )
