"""Tests for solved_today: every way of not getting an answer.

"Cannot check" is not "not solved". Each of these must report
``checked=False``, because the consumer treats an unreadable ledger as a
condition worth notifying about while an honest "nothing solved yet" is just
the ordinary state of a morning.

The integrity key matters as much as the ledger: without it a credit cannot be
verified, and an unverified credit is worth an hour of gaming time.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING

from leetcode_guard.solved_today import solved_today

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime.now(tz=UTC).astimezone()


class TestUnreadableLedger:
    """The file itself cannot be turned into entries."""

    def test_a_missing_ledger(self, tmp_path: Path, hmac_key: Path) -> None:
        """Deleting the ledger must not silently mean "nothing solved".

        Args:
            tmp_path: pytest's temporary directory.
            hmac_key: An isolated signing key.
        """
        answer = solved_today(ledger_path=tmp_path / "absent.json", key_file=hmac_key)
        assert answer.checked is False
        assert "cannot read the ledger" in answer.reason

    def test_unparsable_json(self, tmp_path: Path, hmac_key: Path) -> None:
        """A truncated write is not an answer.

        Args:
            tmp_path: pytest's temporary directory.
            hmac_key: An isolated signing key.
        """
        broken = tmp_path / "l.json"
        broken.write_text("{ not json", encoding="utf-8")
        answer = solved_today(ledger_path=broken, key_file=hmac_key)
        assert answer.checked is False
        assert "not valid JSON" in answer.reason

    def test_no_entries_array(self, tmp_path: Path, hmac_key: Path) -> None:
        """A structurally wrong ledger is not an empty one.

        Args:
            tmp_path: pytest's temporary directory.
            hmac_key: An isolated signing key.
        """
        odd = tmp_path / "l.json"
        odd.write_text(json.dumps({"version": 1}), encoding="utf-8")
        answer = solved_today(ledger_path=odd, key_file=hmac_key)
        assert answer.checked is False
        assert "no entries array" in answer.reason

    def test_a_json_document_that_is_not_an_object(
        self, tmp_path: Path, hmac_key: Path
    ) -> None:
        """Valid JSON of the wrong shape is still not a ledger.

        Args:
            tmp_path: pytest's temporary directory.
            hmac_key: An isolated signing key.
        """
        odd = tmp_path / "l.json"
        odd.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        assert solved_today(ledger_path=odd, key_file=hmac_key).checked is False

    def test_a_non_dict_entry_is_skipped(self, tmp_path: Path, hmac_key: Path) -> None:
        """One junk row must not abort the whole read.

        Args:
            tmp_path: pytest's temporary directory.
            hmac_key: An isolated signing key.
        """
        odd = tmp_path / "l.json"
        odd.write_text(
            json.dumps({"version": 1, "entries": ["junk", 7]}), encoding="utf-8"
        )
        answer = solved_today(ledger_path=odd, key_file=hmac_key)
        assert (answer.checked, answer.solved) == (True, False)


class TestUnusableKey:
    """Without the key nothing can be verified, so nothing can be trusted."""

    def test_a_missing_key(self, tmp_path: Path, missing_key: Path) -> None:
        """A key path that does not exist is a cannot-check.

        Args:
            tmp_path: pytest's temporary directory.
            missing_key: A path with no key at it.
        """
        ledger = tmp_path / "l.json"
        ledger.write_text(json.dumps({"version": 1, "entries": []}), encoding="utf-8")
        answer = solved_today(ledger_path=ledger, key_file=missing_key)
        assert answer.checked is False
        assert "integrity key" in answer.reason

    def test_an_empty_key(self, tmp_path: Path) -> None:
        """A truncated key file is as unusable as a missing one.

        Args:
            tmp_path: pytest's temporary directory.
        """
        empty = tmp_path / "hmac.key"
        empty.write_bytes(b"")
        ledger = tmp_path / "l.json"
        ledger.write_text(json.dumps({"version": 1, "entries": []}), encoding="utf-8")
        assert solved_today(ledger_path=ledger, key_file=empty).checked is False
