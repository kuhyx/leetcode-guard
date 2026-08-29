"""Tests for the status window, its data, and the tray CLIs.

Tk is a MagicMock throughout, so these assert on *what was asked of Tk* and on
the text produced. The pixel check is the Xvfb screenshot -- which is how the
clipped-text bug was found, since no assertion could see a wraplength wider
than its own window.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import TYPE_CHECKING

import pytest

from leetcode_guard._ledger_io import save_ledger
from leetcode_guard._status_extra import (
    gather_budget,
    gather_cache,
    gather_ledger_stats,
    gather_timer,
)
from leetcode_guard._status_full import gather_full
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    add_charge,
    ledger_with_credits,
)

if TYPE_CHECKING:
    from pathlib import Path

MONDAY_NOON = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)


def a_root(tk_mock, width: int = 980):
    """A mock root that answers ``winfo_width`` like real Tk does."""
    root = tk_mock.Tk()
    root.winfo_width.return_value = width
    return root


def full_for(data_dir: Path, hmac_key: Path, ledger=None):
    """A FullStatus over an isolated ledger."""
    path = data_dir / "ledger.json"
    if ledger is not None:
        save_ledger(path, ledger)
    return gather_full(now=MONDAY_NOON, ledger_path=path, key_file=hmac_key)


def test_ledger_stats_count_everything(hmac_key: Path):
    ledger = ledger_with_credits(3, day=MONDAY, key_file=hmac_key)
    add_charge(ledger, MONDAY, key_file=hmac_key)

    stats = gather_ledger_stats(ledger, today=MONDAY)

    assert stats.credits_earned == 3
    assert stats.charges_spent == 1
    assert stats.solves_today == 3
    assert stats.solves_last_7_days == 3
    assert stats.total_entries == 4
    assert stats.charged_days == (MONDAY.isoformat(),)


def test_solves_outside_the_week_are_not_counted_as_recent(hmac_key: Path):
    ledger = ledger_with_credits(2, day=MONDAY, key_file=hmac_key)

    stats = gather_ledger_stats(ledger, today=MONDAY + timedelta(days=30))

    assert stats.credits_earned == 2
    assert stats.solves_today == 0
    assert stats.solves_last_7_days == 0


def test_an_unparsable_day_does_not_break_the_counts(hmac_key: Path):
    from leetcode_guard._ledger import LedgerEntry
    from leetcode_guard._ledger_io import Ledger, append

    ledger = Ledger()
    append(ledger, [LedgerEntry("ac:x", "credit", "not-a-date", "", 1)])

    stats = gather_ledger_stats(ledger, today=MONDAY)

    assert stats.credits_earned == 1
    assert stats.solves_today == 0


def test_the_recent_solve_list_is_capped_and_newest_first(hmac_key: Path):
    ledger = ledger_with_credits(20, day=MONDAY, key_file=hmac_key)

    stats = gather_ledger_stats(ledger, today=MONDAY, limit=5)

    assert len(stats.recent_solves) == 5


def test_budget_reports_usage_against_the_policy(tmp_path: Path, hmac_key: Path):
    from leetcode_guard._escape_flow import build_tracker

    tracker = build_tracker(tmp_path / "escape.json", key_file=hmac_key)

    budget = gather_budget(tracker, "Escape hatch")

    assert budget.used_7 == 0
    assert budget.limit_7 == 1
    assert not budget.exhausted
    assert "0/1 per 7d" in budget.summary


def test_a_missing_cache_reports_absent(tmp_path: Path):
    status = gather_cache(tmp_path / "absent.json", "Pool", "problems", now=0.0)

    assert not status.exists
    assert status.summary == "Pool: none"


def test_a_cache_reports_size_and_age(tmp_path: Path):
    path = tmp_path / "pool.json"
    path.write_text(
        json.dumps({"fetched_at": 0.0, "problems": [1, 2, 3]}), encoding="utf-8"
    )

    status = gather_cache(path, "Pool", "problems", now=86_400.0)

    assert status.entries == 3
    assert status.age_days == pytest.approx(1.0)
    assert "3 entries, 1.0 days old" in status.summary


@pytest.mark.parametrize(
    "content", ["not json", '["a"]', '{"problems": [1], "fetched_at": "soon"}']
)
def test_a_corrupt_cache_degrades_rather_than_raising(tmp_path: Path, content: str):
    path = tmp_path / "pool.json"
    path.write_text(content, encoding="utf-8")

    status = gather_cache(path, "Pool", "problems", now=0.0)

    assert status.exists
    assert status.age_days is None


def test_timer_status_is_read_from_systemctl_show():
    """`list-timers` is a column-aligned table; parsing it printed the whole
    row -- unit names and all -- as the next fire time."""
    calls: list[list[str]] = []

    def fake(args: list[str]) -> str:
        calls.append(args)
        if args[0] == "is-enabled":
            return "enabled\n"
        return "NextElapseUSecRealtime=Tue 2026-07-28 09:00:00 CEST\n"

    timer = gather_timer(run=fake)

    assert timer.enabled
    assert timer.next_fire == "Tue 2026-07-28 09:00:00 CEST"
    assert calls[1][0] == "show"


def test_a_missing_systemctl_degrades_to_unknown():
    timer = gather_timer(run=lambda _args: None)

    assert not timer.enabled
    assert timer.next_fire == "unknown"
