"""``--status`` says how the credits were priced."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard import _constants
from leetcode_guard._difficulty import difficulty_row
from leetcode_guard._ledger_entries import credit_entry
from leetcode_guard._ledger_io import Ledger, append, save_ledger
from leetcode_guard._status import format_status, gather_status, weighting_line
from leetcode_guard.tests._ledger_fixtures import MONDAY, NOW, submission

if TYPE_CHECKING:
    from pathlib import Path


def test_no_solves_no_line():
    assert weighting_line({"Easy": 0, "Medium": 0, "Hard": 0, "unknown": 0}) is None


def test_the_line_names_each_weight():
    line = weighting_line({"Easy": 3, "Medium": 2, "Hard": 1, "unknown": 0})

    assert line == "priced     Easy x1: 3, Medium x2: 2, Hard x4: 1"


def test_unknown_difficulty_is_called_out():
    line = weighting_line({"Easy": 1, "Medium": 0, "Hard": 0, "unknown": 2})

    assert line is not None
    assert line.endswith("no difficulty yet (counted Easy): 2")


def test_status_prices_credits_from_the_signed_cache(data_dir: Path, hmac_key: Path):
    ledger = Ledger()
    append(
        ledger,
        [
            credit_entry(submission("1", "m"), day=MONDAY, now=NOW, key_file=hmac_key),
            credit_entry(submission("2", "e"), day=MONDAY, now=NOW, key_file=hmac_key),
        ],
    )
    save_ledger(_constants.LEDGER_FILE, ledger)
    rows = Ledger()
    append(rows, [difficulty_row("m", "Medium", now=NOW, key_file=hmac_key)])
    save_ledger(_constants.DIFFICULTY_FILE, rows)

    snapshot = gather_status(now=NOW, key_file=hmac_key)
    text = format_status(snapshot)

    assert snapshot.credits == 2 + 1
    assert snapshot.solves == {"Easy": 0, "Medium": 1, "Hard": 0, "unknown": 1}
    lines = text.splitlines()
    assert lines[1].startswith("credits    3 earned")
    assert lines[2].startswith("priced     Easy x1: 0, Medium x2: 1")
