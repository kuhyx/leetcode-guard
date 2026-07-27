"""Turn accepted submissions into credits, and seed the very first run.

Two operations, one of which exists purely to stop the gate being useless on
day one.

**Harvest.** Every accepted submission whose id is not already in the ledger
becomes one credit. No cap, no timestamp window. Because the dedupe key is
LeetCode's submission id:

* a solve from *before* the lock engaged counts, with no special case;
* polling every 30 seconds is idempotent;
* "no cap" is literally true -- ten solves are ten credits.

**Seed.** On the very first run the recent-accepted feed is full of work done
before this tool existed. Harvesting it would mint ~20 credits and buy three
weeks of unlocks, so the gate would never once gate. Seeding records those same
ids as zero-value ``seen`` markers instead, which makes the first run require
one *fresh* solve.

Seeding keys off the presence of a ``bootstrap:`` entry, not off the ledger
file being absent -- an empty-but-present file must still seed.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard._ledger import (
    BOOTSTRAP,
    LedgerEntry,
    bootstrap_entry,
    credit_entry,
    seen_entry,
)
from leetcode_guard._ledger_io import Ledger, append, save_ledger
from leetcode_guard._submissions import ProbeStatus, SolveProbe

if TYPE_CHECKING:
    from datetime import date, datetime
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)


@dataclass(frozen=True)
class HarvestResult:
    """What one harvest pass found."""

    new_credits: tuple[LedgerEntry, ...]
    already_known: int
    status: ProbeStatus
    reason: str

    @property
    def gained(self) -> int:
        """How many credits were minted."""
        return len(self.new_credits)


def needs_seeding(ledger: Ledger) -> bool:
    """Whether this ledger has never been initialised."""
    return not ledger.of_kind(BOOTSTRAP)


def seed_ledger(
    ledger: Ledger,
    probe: SolveProbe,
    *,
    day: date,
    now: datetime,
    path: Path,
    key_file: Path | None = None,
) -> int:
    """Record pre-existing submissions as zero-value markers.

    Refuses to seed from an unverifiable probe. Seeding off a probe we could
    not read would write a bootstrap marker covering nothing, and the next tick
    would then harvest the whole recent feed as credits -- exactly the outcome
    seeding exists to prevent.

    Returns:
        How many submissions were marked, or ``-1`` if seeding was declined.
    """
    if probe.status is not ProbeStatus.OK:
        _logger.warning(
            "declining to seed the ledger from an unverifiable probe (%s) -- "
            "will retry",
            probe.reason,
        )
        return -1

    markers = [
        seen_entry(submission, day=day, now=now, key_file=key_file)
        for submission in probe.submissions
    ]
    markers.append(
        bootstrap_entry(
            day=day, now=now, seeded=len(probe.submissions), key_file=key_file
        )
    )
    append(ledger, markers)
    save_ledger(path, ledger)
    _logger.warning(
        "seeded a new ledger with %d pre-existing submissions -- they are "
        "recorded as already-seen and grant no credit, so the first unlock "
        "requires a fresh solve",
        len(probe.submissions),
    )
    return len(probe.submissions)


def harvest(
    ledger: Ledger,
    probe: SolveProbe,
    *,
    day: date,
    now: datetime,
    key_file: Path | None = None,
) -> HarvestResult:
    """Mint credits for submissions the ledger has not seen.

    Args:
        ledger: The loaded ledger. **Not** mutated -- the caller decides
            whether to persist.
        probe: The solve probe. An unverifiable one yields nothing and carries
            its status through untouched, so callers can tell "no new solves"
            apart from "could not look".
        day: Today's local date, stamped onto new credits.
        now: Current time.
        key_file: HMAC key override, for tests.

    Returns:
        The new credit entries and a count of what was already known.
    """
    if probe.status is not ProbeStatus.OK:
        return HarvestResult(
            new_credits=(),
            already_known=0,
            status=probe.status,
            reason=probe.reason,
        )

    fresh: list[LedgerEntry] = []
    known = 0
    for submission in probe.submissions:
        if ledger.has(f"ac:{submission.submission_id}"):
            known += 1
            continue
        fresh.append(credit_entry(submission, day=day, now=now, key_file=key_file))

    return HarvestResult(
        new_credits=tuple(fresh),
        already_known=known,
        status=ProbeStatus.OK,
        reason=f"{len(fresh)} new, {known} already credited",
    )


def commit_harvest(ledger: Ledger, result: HarvestResult, path: Path) -> bool:
    """Persist harvested credits.

    Returns:
        Whether anything was written.
    """
    if not result.new_credits:
        return False
    append(ledger, list(result.new_credits))
    return save_ledger(path, ledger)
