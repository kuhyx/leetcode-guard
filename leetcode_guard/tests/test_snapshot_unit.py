"""The snapshot's ``status.unit`` block: data only, ``null`` for unknown."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard import _status_full, _status_timer
from leetcode_guard.tests.test_snapshot import a_snapshot

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_the_unit_block_is_data_with_null_for_unknown(
    monkeypatch: pytest.MonkeyPatch, data_dir: Path, hmac_key: Path
):
    """No curriculum or tutor files: unknown with nulls, and no prose for the app."""
    monkeypatch.setattr(
        _status_full,
        "gather_timer",
        lambda: _status_timer.TimerStatus(enabled=True, next_fire="", detail=""),
    )

    unit = a_snapshot(data_dir, hmac_key)["status"]["unit"]

    assert (unit["source"], unit["phase"], unit["leads_with"]) == (
        "unknown",
        "none",
        "problems",
    )
    assert unit["solved"] is None
    assert unit["theory_minutes_today"] is None
    assert unit["theory_credits_today"] == 0
    assert "lead_reason" not in unit
