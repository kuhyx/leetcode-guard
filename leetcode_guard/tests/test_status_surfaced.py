"""Tests that the status view surfaces integrity, clock and key problems."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from leetcode_guard._ledger import LedgerEntry
from leetcode_guard._ledger_io import Ledger, append, save_ledger
from leetcode_guard._status import (
    format_status,
    gather_status,
    snapshot_dict,
)
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    add_charge,
    forged_credit,
    ledger_with_credits,
)
from leetcode_guard.tests._status_fixtures import MONDAY_NOON, status_at

if TYPE_CHECKING:
    from pathlib import Path


def test_integrity_problems_are_surfaced(tmp_path: Path, hmac_key: Path):
    """Forged and malformed credits are counted and named in the text."""
    path = tmp_path / "ledger.json"
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    append(ledger, [forged_credit()])
    append(ledger, [LedgerEntry("bad", "credit", "2026-08-10", "", 1)])
    save_ledger(path, ledger)

    snapshot = status_at(tmp_path, hmac_key, ledger_path=path)

    assert snapshot.balance.tampered == 2
    assert snapshot.balance.discounted == 2
    assert "tampered" in format_status(snapshot)
    assert "refused" in format_status(snapshot)


def test_an_untrusted_clock_is_surfaced(tmp_path: Path, hmac_key: Path):
    """A charge dated after now marks the clock untrusted in the text."""
    path = tmp_path / "ledger.json"
    ledger = Ledger()
    add_charge(ledger, MONDAY.replace(day=12), key_file=hmac_key)
    save_ledger(path, ledger)

    snapshot = status_at(tmp_path, hmac_key, ledger_path=path)

    assert not snapshot.clock_trusted
    assert "UNTRUSTED" in format_status(snapshot)


def test_an_unreadable_key_is_surfaced(tmp_path: Path, missing_key: Path):
    """A missing HMAC key reports integrity off."""
    snapshot = status_at(tmp_path, missing_key)

    assert not snapshot.balance.integrity_ok
    assert "integrity  OFF" in format_status(snapshot)


def test_unparsable_rows_are_surfaced(tmp_path: Path, hmac_key: Path):
    """Unparsable ledger rows are counted and reported as unreadable."""
    path = tmp_path / "ledger.json"
    path.write_text('{"version": 1, "entries": [{"junk": 1}]}', encoding="utf-8")

    snapshot = status_at(tmp_path, hmac_key, ledger_path=path)

    assert snapshot.balance.unparsable == 1
    assert "unreadable" in format_status(snapshot)


def test_the_shortfall_line_is_singular_for_one(tmp_path: Path, hmac_key: Path):
    """A one-solve shortfall uses the singular wording."""
    snapshot = status_at(tmp_path, hmac_key)

    assert "1 more solve to unlock" in format_status(snapshot)


def test_snapshot_dict_is_plain_data(tmp_path: Path, hmac_key: Path):
    """The snapshot dict survives a JSON round trip."""
    snapshot = status_at(tmp_path, hmac_key)

    data = snapshot_dict(snapshot)

    assert data["day"] == "2026-08-10"
    # The requirement is JSON-serialisability for the MCP server, not any
    # particular container type: asdict leaves tuples as tuples and json
    # renders those as arrays.
    assert json.loads(json.dumps(data))["day"] == "2026-08-10"


@pytest.mark.usefixtures("data_dir")
def test_defaults_resolve_to_the_isolated_paths():
    """With no paths given, status reads the default data dir."""
    snapshot = gather_status(now=MONDAY_NOON)

    assert snapshot.verdict.locked
