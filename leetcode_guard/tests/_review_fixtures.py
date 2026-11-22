"""Builders for the review-minute tests: tutor rows and the poll, in the scratch world."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from leetcode_guard._ledger_entries import credit_entry
from leetcode_guard._ledger_io import Ledger, append, load_ledger
from leetcode_guard._theory_credit import TheoryPoll, poll_theory
from leetcode_guard.tests._ledger_fixtures import submission
from leetcode_guard.tests._theory_scenario import states
from leetcode_guard.tests._tutor_fixtures import (
    ALGO,
    review_row,
    teaching_row,
    write_tutor,
)

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 11, 24, 12, 0).astimezone()  # a Tuesday: the day costs 2
DAY = NOW.date()
Rows = list[dict[str, object]]


def lessons(key: Path, module: str, n: int, tag: str = "l") -> Rows:
    """``n`` one-minute lesson rows on ``module``, all ended today."""
    return [
        teaching_row(
            f"{tag}{module}-m{i}",
            1,
            ended=NOW - timedelta(minutes=i + 1),
            key_file=key,
            where=(ALGO, module),
        )
        for i in range(n)
    ]


def reviews(key: Path, module: str, n: int, tag: str = "r") -> Rows:
    """``n`` one-minute tagged review rows on ``module``, all ended today."""
    return [
        review_row(
            f"{tag}{module}-m{i}",
            1,
            ended=NOW - timedelta(minutes=i + 1),
            key_file=key,
            where=(ALGO, module),
        )
        for i in range(n)
    ]


def put(*groups: Rows) -> None:
    """The tutor's C1 file holds exactly these rows."""
    write_tutor("ledger.json", [row for group in groups for row in group])


def poll(ledger: Ledger, data_dir: Path, key: Path) -> TheoryPoll:
    """One poll at :data:`NOW` against the scratch ledger file."""
    return poll_theory(ledger, data_dir / "ledger.json", day=DAY, now=NOW, key_file=key)


def theory_rows(ledger: Ledger) -> list[tuple[str, str, str]]:
    """(unit, minutes, reviews) of today's ``theory:`` rows, in id order."""
    rows = [e for e in ledger.entries.values() if e.entry_id.startswith("theory:")]
    rows.sort(key=lambda e: int(e.entry_id.rsplit(":", 1)[1]))
    return [
        (e.detail["unit"], e.detail["minutes"], e.detail.get("reviews", ""))
        for e in rows
    ]


def finish_unit_a(data_dir: Path, key: Path) -> Ledger:
    """a done and a1 solved: the machine moves on to THEORY(b)."""
    states(key, "a")
    ledger = load_ledger(data_dir / "ledger.json", key_file=key)
    append(
        ledger, [credit_entry(submission("1", "a1"), day=DAY, now=NOW, key_file=key)]
    )
    return ledger
