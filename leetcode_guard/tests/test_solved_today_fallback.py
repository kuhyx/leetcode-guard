"""Tests for solved_today: placing credits that carry no submission time.

The ``day`` key is stamped by the *harvesting* run, so it runs late relative to
the real solve. It is only ever a fallback: it may miss a late-night solve, and
it must never invent one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from leetcode_guard._ledger import LedgerEntry, sign
from leetcode_guard._ledger_entries import credit_entry
from leetcode_guard._ledger_io import Ledger, append, save_ledger
from leetcode_guard._submissions import AcSubmission
from leetcode_guard.solved_today import solved_today

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

NOW = datetime.now(tz=UTC).astimezone()


def _submission(submission_id: str, *, at: datetime) -> AcSubmission:
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


def _write(path: Path, entries: list[LedgerEntry]) -> Path:
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


def _credit(path: Path, *, at: datetime, key_file: Path, ident: str = "ac:1") -> Path:
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
        _submission(ident, at=at), day=at.date(), now=at, key_file=key_file
    )
    return _write(path, [entry])


class TestTheDayKeyFallback:
    """Credits with no usable submission time still have to be placed."""

    def test_a_missing_submitted_at_falls_back_to_the_day(
        self, tmp_path: Path, hmac_key: Path
    ) -> None:
        """Older credits predate the field and must still count.

        Args:
            tmp_path: pytest's temporary directory.
            hmac_key: An isolated signing key.
        """
        entry = sign(
            LedgerEntry(
                entry_id="ac:old",
                kind="credit",
                day=NOW.date().isoformat(),
                created_at=NOW.isoformat(),
                amount=1,
                detail={"source": "leetcode"},
            ),
            key_file=hmac_key,
        )
        path = _write(tmp_path / "l.json", [entry])
        assert solved_today(ledger_path=path, key_file=hmac_key).solved is True

    def test_an_unparsable_submitted_at_is_reported(
        self, tmp_path: Path, hmac_key: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Corrupt data falls back loudly rather than crashing.

        Args:
            tmp_path: pytest's temporary directory.
            hmac_key: An isolated signing key.
            caplog: pytest's log capture.
        """
        entry = sign(
            LedgerEntry(
                entry_id="ac:bad",
                kind="credit",
                day=NOW.date().isoformat(),
                created_at=NOW.isoformat(),
                amount=1,
                detail={"submitted_at": "not-a-number"},
            ),
            key_file=hmac_key,
        )
        path = _write(tmp_path / "l.json", [entry])
        assert solved_today(ledger_path=path, key_file=hmac_key).solved is True
        assert "unparsable submitted_at" in caplog.text

    def test_a_stale_day_key_does_not_count(
        self, tmp_path: Path, hmac_key: Path
    ) -> None:
        """The fallback can miss a late solve; it must never invent one.

        Args:
            tmp_path: pytest's temporary directory.
            hmac_key: An isolated signing key.
        """
        entry = sign(
            LedgerEntry(
                entry_id="ac:old",
                kind="credit",
                day="2020-01-01",
                created_at=NOW.isoformat(),
                amount=1,
                detail={"source": "leetcode"},
            ),
            key_file=hmac_key,
        )
        path = _write(tmp_path / "l.json", [entry])
        assert solved_today(ledger_path=path, key_file=hmac_key).solved is False
