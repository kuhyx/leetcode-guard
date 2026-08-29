"""Ledger test helpers.

Every fixture here passes an explicit ``key_file`` inside ``tmp_path``. No test
ever signs or verifies against ``/etc/workout-locker/hmac.key``, so the suite
neither depends on that file existing nor produces entries that would verify
against the real production key.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
import secrets
from typing import TYPE_CHECKING

from leetcode_guard._ledger import LedgerEntry, sign
from leetcode_guard._ledger_entries import charge_entry, credit_entry
from leetcode_guard._ledger_io import Ledger, append
from leetcode_guard._submissions import AcSubmission

if TYPE_CHECKING:
    from pathlib import Path

# Deliberately a week that falls AFTER GATE_START_DATE. The gate is inert
# before its start date, so fixtures dated earlier would make every scenario
# return UNLOCKED_NOT_STARTED and quietly stop testing anything.
MONDAY = date(2026, 8, 10)
TUESDAY = date(2026, 8, 11)
WEDNESDAY = date(2026, 8, 12)
THURSDAY = date(2026, 8, 13)
FRIDAY = date(2026, 8, 14)
SATURDAY = date(2026, 8, 15)
SUNDAY = date(2026, 8, 16)

NOW = datetime(2026, 8, 10, 9, 0, tzinfo=UTC)


def make_hmac_key(directory: Path) -> Path:
    """Write a real 32-byte key into ``directory``.

    The ``hmac_key`` fixture in ``conftest.py`` wraps this. Fixtures live there
    rather than here so nothing has to be registered as a pytest plugin.
    """
    path = directory / "hmac.key"
    path.write_bytes(secrets.token_bytes(32))
    path.chmod(0o600)
    return path


def submission(
    submission_id: str, slug: str = "two-sum", *, lang: str = "python3"
) -> AcSubmission:
    """A minimal accepted submission."""
    return AcSubmission(
        submission_id=submission_id,
        title=slug,
        title_slug=slug,
        timestamp=1_700_000_000,
        lang=lang,
    )


def credits_for(
    count: int, *, day: date, now: datetime, key_file: Path
) -> list[LedgerEntry]:
    """``count`` distinct signed credits."""
    return [
        credit_entry(submission(f"sub-{index}"), day=day, now=now, key_file=key_file)
        for index in range(count)
    ]


def ledger_with_credits(
    count: int, *, day: date, key_file: Path, now: datetime = NOW
) -> Ledger:
    """A ledger holding ``count`` valid credits and nothing else."""
    ledger = Ledger()
    append(ledger, credits_for(count, day=day, now=now, key_file=key_file))
    return ledger


def add_charge(
    ledger: Ledger, day: date, *, key_file: Path, now: datetime = NOW
) -> None:
    """Record a settled day."""
    append(ledger, [charge_entry(day, now=now, key_file=key_file)])


def forged_credit(entry_id: str = "ac:forged", *, day: date = MONDAY) -> LedgerEntry:
    """An unsigned credit, as a hand-edited ledger file would contain."""
    return LedgerEntry(
        entry_id=entry_id,
        kind="credit",
        day=day.isoformat(),
        created_at=NOW.isoformat(),
        amount=1,
        signature=None,
    )


def foreign_credit(entry_id: str = "ac:foreign", *, key_file: Path) -> LedgerEntry:
    """A validly signed credit that claims to come from another device."""
    return sign(
        LedgerEntry(
            entry_id=entry_id,
            kind="credit",
            day=MONDAY.isoformat(),
            created_at=NOW.isoformat(),
            amount=1,
            device="phone",
        ),
        key_file=key_file,
    )
