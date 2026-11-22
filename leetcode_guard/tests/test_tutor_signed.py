"""Reading the tutor's signed files: only verified rows, "cannot check" as None."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
from typing import TYPE_CHECKING

from leetcode_guard import _tutor_signed
from leetcode_guard._tutor_signed import module_done, signed_rows, teaching_minutes
from leetcode_guard.tests._tutor_fixtures import (
    ALGO,
    state_row,
    teaching_row,
    write_tutor,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

NOON = datetime(2026, 11, 22, 12, 0).astimezone()
DAY = NOON.date()


def test_a_row_the_tutor_library_signed_verifies(hmac_key: Path):
    """Cross-library: earned_time signs, gatelock verifies, the row is kept."""
    write_tutor(
        "ledger.json", [teaching_row("s-m12", 12, ended=NOON, key_file=hmac_key)]
    )

    rows = signed_rows("ledger.json", key_file=hmac_key)

    assert rows is not None
    assert [row["entry_id"] for row in rows] == ["s-m12"]


def test_an_edited_row_is_dropped_with_a_warning(
    hmac_key: Path, caplog: pytest.LogCaptureFixture
):
    """Raising ``minutes`` after signing breaks the HMAC: never counted."""
    forged = teaching_row("s-m12", 12, ended=NOON, key_file=hmac_key)
    detail = forged["detail"]
    assert isinstance(detail, dict)
    detail["minutes"] = 600
    write_tutor("ledger.json", [forged, "not a row"])

    with caplog.at_level(logging.WARNING):
        rows = signed_rows("ledger.json", key_file=hmac_key)

    assert rows == []
    assert "2 unverified rows ignored" in caplog.text


def test_cannot_check_is_none_never_empty(
    hmac_key: Path, missing_key: Path, caplog: pytest.LogCaptureFixture
):
    """Missing file, bad shape, unreadable key: ``None``, each logged."""
    with caplog.at_level(logging.WARNING):
        assert signed_rows("ledger.json", key_file=hmac_key) is None
        path = write_tutor("ledger.json", [])
        path.write_text(json.dumps({"entries": "x"}), encoding="utf-8")
        assert signed_rows("ledger.json", key_file=hmac_key) is None
        path.write_text("[]", encoding="utf-8")
        assert signed_rows("ledger.json", key_file=hmac_key) is None
        assert signed_rows("ledger.json", key_file=missing_key) is None

    assert "cannot check" in caplog.text
    assert "HMAC key unreadable" in caplog.text


def test_the_latest_state_row_wins(hmac_key: Path):
    """By ``at``, then by file order; malformed rows are ignored."""
    rows = [
        state_row("bits", done=True, at=20.0, key_file=hmac_key),
        state_row("bits", done=False, at=10.0, key_file=hmac_key),
        state_row("trees", done=False, at=5.0, key_file=hmac_key),
        state_row("trees", done=True, at=5.0, key_file=hmac_key),
        {"kind": "credit", "detail": {"subject": ALGO, "module": "x"}},
        {"kind": "module_state", "detail": "x"},
        {
            "kind": "module_state",
            "detail": {"subject": ALGO, "module": "y", "done": 1, "at": 1.0},
        },
        {
            "kind": "module_state",
            "detail": {"subject": ALGO, "module": "z", "done": True, "at": True},
        },
        {
            "kind": "module_state",
            "detail": {"subject": 1, "module": "z", "done": True, "at": 1},
        },
        {
            "kind": "module_state",
            "detail": {"subject": ALGO, "module": 2, "done": True, "at": 1},
        },
    ]

    assert module_done(rows) == {(ALGO, "bits"): True, (ALGO, "trees"): True}


def test_teaching_minutes_follow_earned_times_rules(hmac_key: Path):
    """Today's teaching rows on the unit's modules; replays pay once, at the minimum."""

    def row(
        entry_id: str,
        minutes: object,
        module: str | None = "prefix-sums",
        subject: str = ALGO,
    ) -> dict[str, object]:
        built = teaching_row(
            entry_id, 1, ended=NOON, key_file=hmac_key, where=(subject, module)
        )
        detail = built["detail"]
        assert isinstance(detail, dict)
        detail["minutes"] = minutes
        return built

    yesterday = teaching_row(
        "old-m9", 9, ended=NOON - timedelta(days=1), key_file=hmac_key
    )
    no_end = row("e-m3", 3)
    no_end_detail = no_end["detail"]
    assert isinstance(no_end_detail, dict)
    no_end_detail["ended_at"] = True
    rows = [
        row("a-m10", 10),
        row("a-m10", 7),  # replayed with a smaller count
        row("b-m5", 5, module="bits"),  # another unit's module
        row("c-m4", 4, module=None),  # a review row: no module
        row("d-m4", 4, subject="other"),
        row("bad1", True),
        row("bad2", 0),
        row("bad3", "5"),
        yesterday,
        no_end,
        {**row("x", 2), "entry_id": None},
        {**row("y", 3), "entry_id": None},
        {**row("w", 3), "kind": "module_state"},
        {**row("v", 3), "detail": "x"},
    ]

    assert teaching_minutes(rows, ALGO, ("prefix-sums",), day=DAY) == 7 + 2 + 3


def test_the_scratch_tutor_dir_is_in_force(tmp_path: Path):
    """The suite never reads the live tutor's files."""
    assert tmp_path / "tutor" == _tutor_signed.TUTOR_DIR
