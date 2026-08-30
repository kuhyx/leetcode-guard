"""Tests for solved_today: the cross-repo "did I solve one today" contract.

steam-backlog-enforcer turns a True here into an extra hour of gaming budget,
so the two properties that matter are that a forged or stale credit cannot
produce one, and that every unreadable state reports ``checked=False`` instead
of a confident "nothing solved".

The solve time comes from ``detail["submitted_at"]``, not the entry's ``day``,
because ``day`` is stamped by the harvesting run: a problem solved at 23:50 and
harvested the next morning carries the next day's key.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from typing import TYPE_CHECKING

from leetcode_guard._ledger import LedgerEntry, sign
from leetcode_guard._ledger_entries import charge_entry, credit_entry
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


class TestCountingTodaysSolves:
    """Which entries earn the hour."""

    def test_a_solve_today_counts(self, tmp_path: Path, hmac_key: Path) -> None:
        """The ordinary case.

        Args:
            tmp_path: pytest's temporary directory.
            hmac_key: An isolated signing key.
        """
        path = _credit(tmp_path / "l.json", at=NOW, key_file=hmac_key)
        answer = solved_today(ledger_path=path, key_file=hmac_key)
        assert (answer.checked, answer.solved, answer.count) == (True, True, 1)
        assert answer.reason == "1 accepted submission today"

    def test_two_solves_are_counted_and_pluralised(
        self, tmp_path: Path, hmac_key: Path
    ) -> None:
        """The count is reported, not just the boolean.

        Args:
            tmp_path: pytest's temporary directory.
            hmac_key: An isolated signing key.
        """
        entries = [
            credit_entry(
                _submission(f"ac:{i}", at=NOW),
                day=NOW.date(),
                now=NOW,
                key_file=hmac_key,
            )
            for i in range(2)
        ]
        path = _write(tmp_path / "l.json", entries)
        answer = solved_today(ledger_path=path, key_file=hmac_key)
        assert answer.count == 2
        assert answer.reason == "2 accepted submissions today"

    def test_yesterdays_solve_does_not_count(
        self, tmp_path: Path, hmac_key: Path
    ) -> None:
        """Yesterday's solve bought yesterday's hour.

        Args:
            tmp_path: pytest's temporary directory.
            hmac_key: An isolated signing key.
        """
        path = _credit(
            tmp_path / "l.json", at=NOW - timedelta(days=1), key_file=hmac_key
        )
        answer = solved_today(ledger_path=path, key_file=hmac_key)
        assert (answer.checked, answer.solved) == (True, False)
        assert answer.reason == "no accepted submission recorded today"

    def test_charges_do_not_stand_in_for_a_solve(
        self, tmp_path: Path, hmac_key: Path
    ) -> None:
        """A settled day can be paid from banked credit or the escape hatch.

        Args:
            tmp_path: pytest's temporary directory.
            hmac_key: An isolated signing key.
        """
        charge = charge_entry(NOW.date(), now=NOW, key_file=hmac_key)
        path = _write(tmp_path / "l.json", [charge])
        assert solved_today(ledger_path=path, key_file=hmac_key).solved is False

    def test_seen_entries_do_not_count(self, tmp_path: Path, hmac_key: Path) -> None:
        """Seeding marks the feed as already-known; it is worth nothing.

        Args:
            tmp_path: pytest's temporary directory.
            hmac_key: An isolated signing key.
        """
        entry = sign(
            LedgerEntry(
                entry_id="ac:seen",
                kind="seen",
                day=NOW.date().isoformat(),
                created_at=NOW.isoformat(),
                amount=0,
                detail={"submitted_at": str(int(NOW.timestamp()))},
            ),
            key_file=hmac_key,
        )
        path = _write(tmp_path / "l.json", [entry])
        assert solved_today(ledger_path=path, key_file=hmac_key).solved is False

    def test_a_forged_credit_is_refused_and_reported(
        self, tmp_path: Path, hmac_key: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Appending JSON by hand must not buy an hour.

        Args:
            tmp_path: pytest's temporary directory.
            hmac_key: An isolated signing key.
            caplog: pytest's log capture.
        """
        path = _credit(tmp_path / "l.json", at=NOW, key_file=hmac_key)
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["entries"][0]["hmac"] = "00" * 32
        path.write_text(json.dumps(raw), encoding="utf-8")
        answer = solved_today(ledger_path=path, key_file=hmac_key)
        assert (answer.checked, answer.solved) == (True, False)
        assert "failed their signature check" in caplog.text

    def test_the_configured_ledger_is_used_when_none_is_given(
        self, data_dir: Path, hmac_key: Path
    ) -> None:
        """The default must resolve at call time, not bind at import.

        Args:
            data_dir: The suite's redirected data directory.
            hmac_key: An isolated signing key.
        """
        _credit(data_dir / "ledger.json", at=NOW, key_file=hmac_key)
        assert solved_today(key_file=hmac_key).solved is True
