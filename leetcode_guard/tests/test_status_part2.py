"""Continued from :mod:`test_status`, split for the 250-line cap."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from leetcode_guard._ledger_io import Ledger, save_ledger
from leetcode_guard._status import format_status, gather_status
from leetcode_guard.tests._ledger_fixtures import MONDAY
from leetcode_guard.tests.test_status import MONDAY_NOON

if TYPE_CHECKING:
    from pathlib import Path


def test_the_debt_is_surfaced_with_the_price(
    tmp_path: Path, hmac_key: Path, debt_starts
):
    debt_starts(MONDAY)
    ledger_path = tmp_path / "ledger.json"
    save_ledger(ledger_path, Ledger())

    snapshot = gather_status(
        now=MONDAY_NOON + timedelta(days=9),
        ledger_path=ledger_path,
        cache_path=tmp_path / "pool.json",
        cookies_path=tmp_path / "cookies.json",
        key_file=hmac_key,
    )
    text = format_status(snapshot)

    assert snapshot.missed_days == 9
    assert snapshot.debt_outstanding == 11
    assert snapshot.cost == 2
    assert "costs 2 (1 +1 debt)" in text
    assert "debt       11 credits outstanding (9 missed days owed 11, 0 repaid)" in text
