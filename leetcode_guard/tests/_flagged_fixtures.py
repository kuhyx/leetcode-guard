"""Builders for the "flagged solve" tests (not collected as tests).

A solve is a ledger credit plus the heartbeats around it, so these helpers
write both: :func:`beat_run` makes the minute-apart heartbeats of one sitting,
:func:`record_of` wraps them into an ``attempts.json`` record, and
:func:`write_credits` signs real credit rows into the redirected ledger.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from leetcode_guard._attempt_model import (
    AttemptRecord,
    Beat,
    Submission,
    day_of,
    record_key,
)
from leetcode_guard._ledger_entries import credit_entry
from leetcode_guard._ledger_io import Ledger, append, save_ledger
from leetcode_guard._submissions import AcSubmission
from leetcode_guard.tests._ledger_fixtures import MONDAY

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

T0 = 1_795_287_000
"""The accept time of the standard solve (a local evening; days via ``day_of``)."""
NOW = datetime.fromtimestamp(T0 + 3600, tz=UTC)
"""A "now" one hour after :data:`T0`, so the standard solve is inside 28 days."""
MINUTE = 60
DAY_SECONDS = 86_400


def beat_run(end: int, count: int, tab: str = "description") -> list[Beat]:
    """``count`` beats one minute apart, the last one at ``end``."""
    return [Beat(end - MINUTE * (count - 1 - index), tab) for index in range(count)]


def record_of(
    slug: str,
    beats: Iterable[Beat],
    *,
    at: int = T0,
    submissions: dict[str, Submission] | None = None,
    theory: str | None = None,
) -> AttemptRecord:
    """The record of ``slug`` on the local day of ``at``."""
    return AttemptRecord(
        day_of(at), slug, list(beats), dict(submissions or {}), theory_at_solve=theory
    )


def records_of(*found: AttemptRecord) -> dict[str, AttemptRecord]:
    """The document's record map, keyed the way the store keys it."""
    return {record_key(item.day, item.slug): item for item in found}


def write_credits(path: Path, rows: Iterable[tuple[str, str, int]], key: Path) -> None:
    """Save a ledger holding one signed credit per ``(id, slug, accepted_at)``."""
    ledger = Ledger()
    append(
        ledger,
        [
            credit_entry(
                AcSubmission(sub_id, slug, slug, at, "python3"),
                day=MONDAY,
                now=NOW,
                key_file=key,
            )
            for sub_id, slug, at in rows
        ],
    )
    save_ledger(path, ledger)


def solve_dict(report: dict[str, Any], slug: str) -> dict[str, Any]:
    """The one measured solve of ``slug`` in a report."""
    (found,) = [item for item in report["measured"] if item["slug"] == slug]
    return found
