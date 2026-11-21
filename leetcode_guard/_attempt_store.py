"""``attempts.json``: heartbeats, submissions and theory snapshots, per day.

Display-only measurement for the problem coach. **Nothing that decides,
charges or credits may read it** -- anyone can edit this file, so a decider
that consulted it would turn "open the editorial" into a bypass
(``test_display_only_imports`` bans it, transitively).

Writers: the status service (:func:`add_beat`) and the one-minute harvester
(:func:`merge_submissions`, :func:`snapshot_theory`). Each write is a
read-modify-write under an exclusive ``flock`` (``_attempt_io.update``), then an
atomic rename, so neither loses the other's update. Every write drops records
more than 180 days old.

Failure modes, all fail-open and all logged at warning; none raises into the
caller for an I/O problem:

* the lock is not obtained within two seconds -> the write is skipped;
* the file is corrupt at write time (unreadable, or the wrong shape) -> it is
  moved aside to ``attempts.json.corrupt`` (replacing an older aside) and a
  fresh document is started, so one bad file cannot stall measurement forever;
* the atomic write fails with ``OSError`` -> the write is reported as failed.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Final

from leetcode_guard._attempt_io import (
    DEFAULT_TIMING,
    Outcome,
    Records,
    load,
    update,
)
from leetcode_guard._attempt_model import (
    THEORY_VALUES,
    AttemptRecord,
    Beat,
    Submission,
    cutoff,
    day_of,
    record_key,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import date
    from pathlib import Path

    from leetcode_guard._attempt_lock import LockTiming

__all__ = [
    "DEDUPE_SECONDS",
    "Outcome",
    "add_beat",
    "load",
    "merge_submissions",
    "snapshot_theory",
]

DEDUPE_SECONDS: Final = 10
"""A same-tab beat closer than this to the previous one is not recorded."""


def add_beat(
    slug: str,
    tab: str,
    *,
    now: float,
    path: Path | None = None,
    timing: LockTiming = DEFAULT_TIMING,
) -> Outcome:
    """Append a heartbeat to the (local day, slug) record.

    Args:
        slug: The problem's ``titleSlug``.
        tab: Which tab was visible (the caller validates it).
        now: The SERVER's clock in unix seconds; never client data. A clock
            that moved backwards is clamped to the previous beat so the list
            stays ascending.
        path: The file, or ``None`` for ``_attempt_paths.ATTEMPTS_FILE``.
        timing: Lock timeout and clock.

    Returns:
        ``WRITTEN``; ``SKIPPED`` when the previous beat of the record has the
        same tab and is under :data:`DEDUPE_SECONDS` old (no write happens);
        or ``FAILED`` (logged at warning).
    """

    def mutate(records: Records, _: date) -> int:
        stamp = int(now)
        key = record_key(day_of(stamp), slug)
        found = records.setdefault(key, AttemptRecord(day_of(stamp), slug))
        if found.beats:
            last = found.beats[-1]
            stamp = max(stamp, last.at)
            if last.tab == tab and stamp - last.at < DEDUPE_SECONDS:
                return 0
        found.beats.append(Beat(stamp, tab))
        return 1

    return update(mutate, now=now, path=path, timing=timing)[0]


def merge_submissions(
    rows: Iterable[tuple[str, str, str, int]],
    *,
    now: float | None = None,
    path: Path | None = None,
    timing: LockTiming = DEFAULT_TIMING,
) -> int:
    """Merge LeetCode submissions into the record of the day they were made.

    Args:
        rows: ``(submission_id, slug, statusDisplay, unix_seconds)``. The
            record for (local day of the timestamp, slug) is created if absent.
            A known id keeps its first status; a row older than the retention
            window is ignored (it would be pruned at once).
        now: The clock for retention; defaults to the current time.
        path: The file, or ``None`` for the configured one.
        timing: Lock timeout and clock.

    Returns:
        How many rows were new. ``0`` as well when the write failed (logged).
    """
    batch = list(rows)
    if not batch:
        return 0

    def mutate(records: Records, today: date) -> int:
        floor, added = cutoff(today), 0
        for sub_id, slug, status, at in batch:
            day = day_of(at)
            if day < floor:
                continue
            found = records.setdefault(record_key(day, slug), AttemptRecord(day, slug))
            if sub_id not in found.submissions:
                found.submissions[sub_id] = Submission(status, at)
                added += 1
        return added

    stamp = time.time() if now is None else now
    return update(mutate, now=stamp, path=path, timing=timing)[1]


def snapshot_theory(
    day: str,
    slug: str,
    theory: str,
    *,
    now: float | None = None,
    path: Path | None = None,
) -> bool:
    """Record the theory state at the moment of the solve, once.

    Args:
        day: The record's local day, ISO (``date.isoformat()``).
        slug: The problem's ``titleSlug``.
        theory: One of :data:`THEORY_VALUES` (the ``Theory`` enum's values).
        now: The clock for retention; defaults to the current time.
        path: The file, or ``None`` for the configured one. The lock timing is
            the default two seconds (this one is tested through ``add_beat``).

    Returns:
        Whether it wrote: only when the record exists and has no snapshot yet.
        A set value is never overwritten.

    Raises:
        ValueError: If ``theory`` is not one of :data:`THEORY_VALUES`.
    """
    if theory not in THEORY_VALUES:
        msg = f"theory must be one of {THEORY_VALUES}, got {theory!r}"
        raise ValueError(msg)

    def mutate(records: Records, _: date) -> int:
        found = records.get(record_key(day, slug))
        if found is None or found.theory_at_solve is not None:
            return 0
        found.theory_at_solve = theory
        return 1

    stamp = time.time() if now is None else now
    return (
        update(mutate, now=stamp, path=path, timing=DEFAULT_TIMING)[0]
        is Outcome.WRITTEN
    )
