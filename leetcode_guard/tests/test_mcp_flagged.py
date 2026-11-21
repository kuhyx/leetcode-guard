"""``get_flagged``: the same report as ``--flagged --json``, read-only."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from leetcode_guard import _attempt_paths, _constants, _mcp
from leetcode_guard._attempt_model import to_document
from leetcode_guard.tests._flagged_fixtures import (
    T0,
    beat_run,
    record_of,
    records_of,
    write_credits,
)
from leetcode_guard.tests.test_mcp import tool_names

if TYPE_CHECKING:
    from pathlib import Path


def test_get_flagged_is_an_exposed_read_only_tool():
    """It is a tool, and its name is none of the banned write-shaped prefixes."""
    assert "get_flagged" in tool_names()


def test_get_flagged_returns_the_report_and_writes_nothing(hmac_key: Path):
    """A flagged solve shows up; the data directory is byte-for-byte unchanged."""
    write_credits(_constants.LEDGER_FILE, [("1", "a", T0)], hmac_key)
    _attempt_paths.ATTEMPTS_FILE.write_text(
        json.dumps(
            to_document(records_of(record_of("a", beat_run(T0, 26), theory="done")))
        ),
        encoding="utf-8",
    )
    data = _constants.DATA_DIR
    before = {path.name: path.read_bytes() for path in data.iterdir()}

    report = _mcp.get_flagged()

    assert [row["slug"] for row in report["flagged"]] == ["a"]
    assert report["threshold_seconds"] == 1200
    assert json.loads(json.dumps(report)) == report
    assert {path.name: path.read_bytes() for path in data.iterdir()} == before
