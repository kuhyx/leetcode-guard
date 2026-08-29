"""The four kinds of ledger entry, each signed as it is built.

Split out of ``_ledger.py`` for the 250-line cap: that module owns the record
and its signature, this one the constructors that use them. The dependency
runs one way, here to there, so the two never form a cycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._daycost import day_cost, day_key

if TYPE_CHECKING:
    from datetime import date, datetime
    from pathlib import Path

    from leetcode_guard._submissions import AcSubmission

from leetcode_guard._ledger import (
    BOOTSTRAP,
    CHARGE,
    CREDIT,
    SEEN,
    SOURCE_LEETCODE,
    SOURCE_SEED,
    LedgerEntry,
    sign,
)


def _iso(now: datetime) -> str:
    """Serialise a timestamp for storage."""
    return now.isoformat()


def credit_entry(
    submission: AcSubmission,
    *,
    day: date,
    now: datetime,
    key_file: Path | None = None,
) -> LedgerEntry:
    """A signed +1 credit for one accepted submission."""
    return sign(
        LedgerEntry(
            entry_id=f"ac:{submission.submission_id}",
            kind=CREDIT,
            day=day_key(day),
            created_at=_iso(now),
            amount=1,
            detail={
                "title_slug": submission.title_slug,
                "lang": submission.lang,
                "source": SOURCE_LEETCODE,
                "submitted_at": str(submission.timestamp),
            },
        ),
        key_file=key_file,
    )


def seen_entry(
    submission: AcSubmission,
    *,
    day: date,
    now: datetime,
    key_file: Path | None = None,
) -> LedgerEntry:
    """A zero-value marker: this submission predates the gate.

    Written during first-run seeding so the same submission can never later be
    harvested as a credit.
    """
    return sign(
        LedgerEntry(
            entry_id=f"ac:{submission.submission_id}",
            kind=SEEN,
            day=day_key(day),
            created_at=_iso(now),
            amount=0,
            detail={"title_slug": submission.title_slug, "source": SOURCE_SEED},
        ),
        key_file=key_file,
    )


def bootstrap_entry(
    *, day: date, now: datetime, seeded: int, key_file: Path | None = None
) -> LedgerEntry:
    """The marker proving seeding has happened.

    Seeding keys off this rather than off the file's absence, so an
    empty-but-present ledger still gets seeded instead of handing out every
    recent submission as a credit.
    """
    return sign(
        LedgerEntry(
            entry_id=f"bootstrap:{day_key(day)}",
            kind=BOOTSTRAP,
            day=day_key(day),
            created_at=_iso(now),
            amount=0,
            detail={"seeded": str(seeded), "source": SOURCE_SEED},
        ),
        key_file=key_file,
    )


def charge_entry(
    day: date,
    *,
    now: datetime,
    source: str = SOURCE_LEETCODE,
    key_file: Path | None = None,
) -> LedgerEntry:
    """A signed debit for one gated day.

    ``source`` records *why* the day was satisfied: normally credits, but also
    an escape hatch or a classified LeetCode outage. Those still write a charge
    -- the day is settled -- and can push the balance negative, which is
    intended: the debt carries and the next day still costs full price.
    """
    return sign(
        LedgerEntry(
            entry_id=f"charge:{day_key(day)}",
            kind=CHARGE,
            day=day_key(day),
            created_at=_iso(now),
            amount=day_cost(day),
            detail={"source": source},
        ),
        key_file=key_file,
    )
