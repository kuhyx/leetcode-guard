"""Tests for solved_today: placing credits that carry no submission time.

The ``day`` key is stamped by the *harvesting* run, so it runs late relative to
the real solve. It is only ever a fallback: it may miss a late-night solve, and
it must never invent one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._ledger import LedgerEntry, sign
from leetcode_guard.solved_today import solved_today
from leetcode_guard.tests._solved_today_fixtures import NOW, write_ledger

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


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
        path = write_ledger(tmp_path / "l.json", [entry])
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
        path = write_ledger(tmp_path / "l.json", [entry])
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
        path = write_ledger(tmp_path / "l.json", [entry])
        assert solved_today(ledger_path=path, key_file=hmac_key).solved is False
