"""Helpers shared by the finish-credit tests: signed C2 flips, one poll, ids."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from leetcode_guard._ledger_entries import credit_entry
from leetcode_guard._ledger_io import append
from leetcode_guard._theory_credit import TheoryPoll, poll_theory
from leetcode_guard.tests._ledger_fixtures import submission
from leetcode_guard.tests._tutor_fixtures import ALGO, state_row, write_tutor

if TYPE_CHECKING:
    from pathlib import Path

    from leetcode_guard._ledger_io import Ledger

NOW = datetime(2026, 11, 24, 12, 0).astimezone()
DAY = NOW.date()
YESTERDAY = (NOW - timedelta(days=1)).timestamp()
TODAY = NOW.timestamp()
A_ID = f"theory-done:{ALGO}:a"
B1_ID = f"theory-done:{ALGO}:b1"


def flips(key: Path, *rows: tuple[str, bool, float]) -> None:
    """C2 rows (module, done, at), the n-th row of a module signed as its n-th."""
    count: dict[str, int] = {}
    signed: list[object] = []
    for module, done, at in rows:
        count[module] = count.get(module, 0) + 1
        signed.append(
            state_row(module, done=done, at=at, key_file=key, n=count[module])
        )
    write_tutor("module_state.json", signed)


def poll(ledger: Ledger, data_dir: Path, key: Path) -> TheoryPoll:
    """One poll against the scratch ledger file."""
    return poll_theory(ledger, data_dir / "ledger.json", day=DAY, now=NOW, key_file=key)


def ids(result: TheoryPoll) -> list[str]:
    """What the poll minted."""
    return [entry.entry_id for entry in result.minted]


def solved_a1(ledger: Ledger, key: Path) -> None:
    """The guard's ledger holds a solve of a's only Easy problem."""
    append(
        ledger, [credit_entry(submission("1", "a1"), day=DAY, now=NOW, key_file=key)]
    )
