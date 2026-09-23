"""The workday-stick penalty: read from wake-alarm's signed file, never re-derived."""

from __future__ import annotations

from datetime import date
import json
from typing import TYPE_CHECKING

from gatelock.log_integrity import compute_entry_hmac
import pytest

from leetcode_guard import _workday_penalty
from leetcode_guard._workday_penalty import workday_penalty_for

if TYPE_CHECKING:
    from pathlib import Path

TUESDAY = date(2026, 8, 11)
WEDNESDAY = date(2026, 8, 12)


@pytest.fixture(autouse=True)
def _signing_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    key = tmp_path / "hmac.key"
    key.write_bytes(b"1" * 32)
    import gatelock.log_integrity

    monkeypatch.setattr(gatelock.log_integrity, "DEFAULT_HMAC_KEY_FILE", key)


def _write(entry: dict[str, object], *, sign: bool = True) -> Path:
    if sign:
        entry["hmac"] = compute_entry_hmac(entry)
    path = _workday_penalty.WORKDAY_PENALTY_FILE
    path.write_text(json.dumps(entry))
    return path


def test_the_penalized_day_is_penalized() -> None:
    _write({"penalty_date": "2026-08-12", "issued_date": "2026-08-11"})
    assert workday_penalty_for(WEDNESDAY) is True


def test_a_different_day_is_not_penalized() -> None:
    _write({"penalty_date": "2026-08-12", "issued_date": "2026-08-11"})
    assert workday_penalty_for(TUESDAY) is False


def test_missing_unreadable_tampered_are_all_no_penalty(tmp_path: Path) -> None:
    assert workday_penalty_for(WEDNESDAY) is False
    path = _write({"penalty_date": "2026-08-12"}, sign=False)
    assert workday_penalty_for(WEDNESDAY) is False
    path.write_text("not json")
    assert workday_penalty_for(WEDNESDAY) is False
    path.write_text("[]")
    assert workday_penalty_for(WEDNESDAY) is False
    path.unlink()
    assert workday_penalty_for(WEDNESDAY) is False
