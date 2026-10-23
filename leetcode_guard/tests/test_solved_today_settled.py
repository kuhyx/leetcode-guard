"""Tests for ``settled_by_credit``: a day paid ahead earns the bonus too.

kuhy, 2026-10-23: the solves of 10-22 paid 10-23's gate, and every bonus
consumer still read "no solve today" -- working ahead forfeited the hour. A
charge sourced ``leetcode`` is written only when verified credits cover the
day (``_gate.decide``), so it is a payment, not a forgiveness. The escape
hatch and the outage path write their own sources and must never count.

``solved`` keeps its meaning -- a solve landed today -- and the new field is
published beside it, so no consumer's reading of the old one silently changes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from leetcode_guard._ledger import SOURCE_ESCAPE, SOURCE_OUTAGE
from leetcode_guard._ledger_entries import charge_entry
from leetcode_guard._ledger_io import Ledger, append, save_ledger
from leetcode_guard._web_server import build_status_payload
from leetcode_guard.solved_today import SolvedToday, solved_today

if TYPE_CHECKING:
    from pathlib import Path

    from leetcode_guard._ledger import LedgerEntry

NOW = datetime.now(tz=UTC).astimezone()


def _write(path: Path, entry: LedgerEntry) -> Path:
    """Save a ledger holding exactly *entry*.

    Args:
        path: Where to write it.
        entry: The entry to store.

    Returns:
        The ledger path.
    """
    ledger = Ledger()
    append(ledger, [entry])
    save_ledger(path, ledger)
    return path


def test_a_day_paid_from_banked_credit_is_settled(
    tmp_path: Path, hmac_key: Path
) -> None:
    """The charge ``decide`` writes when the balance covers the day.

    Args:
        tmp_path: pytest's temporary directory.
        hmac_key: An isolated signing key.
    """
    charge = charge_entry(NOW.date(), now=NOW, key_file=hmac_key)
    answer = solved_today(
        ledger_path=_write(tmp_path / "l.json", charge), key_file=hmac_key
    )
    assert answer.checked is True
    assert answer.settled_by_credit is True
    assert answer.solved is False


@pytest.mark.parametrize("source", [SOURCE_ESCAPE, SOURCE_OUTAGE])
def test_a_forgiven_day_is_not_settled_by_credit(
    tmp_path: Path, hmac_key: Path, source: str
) -> None:
    """An escaped or outage day overdraws; it was never paid for.

    Args:
        tmp_path: pytest's temporary directory.
        hmac_key: An isolated signing key.
        source: The forgiving path that wrote the charge.
    """
    charge = charge_entry(NOW.date(), now=NOW, source=source, key_file=hmac_key)
    answer = solved_today(
        ledger_path=_write(tmp_path / "l.json", charge), key_file=hmac_key
    )
    assert answer.settled_by_credit is False


def test_yesterdays_charge_settles_only_yesterday(
    tmp_path: Path, hmac_key: Path
) -> None:
    """The charge counts for the day it names, never the next one.

    Args:
        tmp_path: pytest's temporary directory.
        hmac_key: An isolated signing key.
    """
    then = NOW - timedelta(days=1)
    charge = charge_entry(then.date(), now=then, key_file=hmac_key)
    answer = solved_today(
        ledger_path=_write(tmp_path / "l.json", charge), key_file=hmac_key
    )
    assert answer.settled_by_credit is False


def test_a_forged_charge_settles_nothing(tmp_path: Path, hmac_key: Path) -> None:
    """Appending a charge by hand must not buy an hour.

    Args:
        tmp_path: pytest's temporary directory.
        hmac_key: An isolated signing key.
    """
    path = _write(
        tmp_path / "l.json", charge_entry(NOW.date(), now=NOW, key_file=hmac_key)
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["entries"][0]["hmac"] = "0" * 64
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert solved_today(ledger_path=path, key_file=hmac_key).settled_by_credit is False


def test_the_endpoint_publishes_it() -> None:
    """The enforcer's fallback transport must see the same fact."""
    answer = SolvedToday(
        checked=True, solved=False, count=0, reason="none", settled_by_credit=True
    )
    with patch("leetcode_guard._web_server.solved_today", return_value=answer):
        payload = build_status_payload()
    assert payload["leetcode"]["settled_by_credit"] is True
