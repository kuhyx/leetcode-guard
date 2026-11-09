"""Continued from :mod:`test_status`, split for the 250-line cap."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from leetcode_guard import _status
from leetcode_guard._ledger_io import Ledger, save_ledger
from leetcode_guard._status import (
    PoolFiles,
    format_status,
    gather_status,
    snapshot_dict,
)
from leetcode_guard.tests._ledger_fixtures import MONDAY, add_charge
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
        now=MONDAY_NOON + timedelta(days=11),  # a Friday: surcharged
        ledger_path=ledger_path,
        pool_files=PoolFiles(
            cache=tmp_path / "pool.json", cookies=tmp_path / "cookies.json"
        ),
        key_file=hmac_key,
    )
    text = format_status(snapshot)

    assert snapshot.debt.missed_days == 11
    assert snapshot.debt.outstanding == 13
    assert snapshot.cost == 2
    assert "costs 2 (1 +1 debt)" in text
    assert (
        "debt       13 credits outstanding (11 missed days owed 13, 0 repaid)" in text
    )


def test_main_exits_one_when_locked(capsys, data_dir: Path):
    exit_code = _status.main([])

    assert exit_code == 1
    assert "state" in capsys.readouterr().out


def test_main_exits_zero_when_unlocked(
    capsys, data_dir: Path, hmac_key: Path, monkeypatch
):
    ledger = Ledger()
    add_charge(ledger, _status.local_today(), key_file=hmac_key)
    monkeypatch.setattr(_status, "load_ledger", lambda *a, **k: ledger)

    assert _status.main([]) == 0


def test_snapshot_dict_keeps_the_flat_mcp_keys(tmp_path: Path, hmac_key: Path):
    """The grouped snapshot is internal: MCP clients still get the flat keys,
    in the order they always had."""
    snapshot = gather_status(
        now=MONDAY_NOON,
        ledger_path=tmp_path / "ledger.json",
        pool_files=PoolFiles(
            cache=tmp_path / "pool.json", cookies=tmp_path / "cookies.json"
        ),
        key_file=hmac_key,
    )

    data = snapshot_dict(snapshot)

    assert list(data) == [
        "day", "weekday", "cost", "debt", "surcharge", "debt_owed", "debt_repaid",
        "debt_outstanding", "missed_days", "credits", "charged", "available",
        "needed", "state", "locked", "reason", "charged_today", "integrity_ok",
        "tampered", "discounted", "unparsable", "clock_trusted", "auth_present",
        "auth_note", "pool_source", "pool_notes", "suggestions", "solves",
    ]  # fmt: skip
    assert data["debt"] == {"owed": 0, "repaid": 0, "missed_days": 0}
    assert data["locked"] is True
    assert data["needed"] == 1
