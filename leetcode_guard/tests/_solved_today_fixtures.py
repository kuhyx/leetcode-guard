"""Ledger builders shared by the ``solved_today`` test modules."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from leetcode_guard._ledger_entries import credit_entry
from leetcode_guard._ledger_io import Ledger, append, save_ledger
from leetcode_guard._submissions import AcSubmission

if TYPE_CHECKING:
    from pathlib import Path

    from leetcode_guard._ledger import LedgerEntry

NOW = datetime.now(tz=UTC).astimezone()


def stamped_submission(submission_id: str, *, at: datetime) -> AcSubmission:
    """An accepted submission stamped at a chosen moment.

    Args:
        submission_id: LeetCode's submission id.
        at: When it was submitted.

    Returns:
        The submission.
    """
    return AcSubmission(
        submission_id=submission_id,
        title="two-sum",
        title_slug="two-sum",
        timestamp=int(at.timestamp()),
        lang="python3",
    )


def write_ledger(path: Path, entries: list[LedgerEntry]) -> Path:
    """Save a ledger holding exactly *entries*.

    Args:
        path: Where to write it.
        entries: The entries to store.

    Returns:
        The ledger path.
    """
    ledger = Ledger()
    append(ledger, entries)
    save_ledger(path, ledger)
    return path


def write_credit(
    path: Path, *, at: datetime, key_file: Path, ident: str = "ac:1"
) -> Path:
    """Write a ledger with one signed credit submitted at *at*.

    Args:
        path: Where to write it.
        at: The submission time.
        key_file: The signing key.
        ident: The submission id.

    Returns:
        The ledger path.
    """
    entry = credit_entry(
        stamped_submission(ident, at=at), day=at.date(), now=at, key_file=key_file
    )
    return write_ledger(path, [entry])
