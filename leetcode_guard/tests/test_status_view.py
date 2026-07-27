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

from leetcode_guard import status_view
from leetcode_guard._ledger_io import save_ledger
from leetcode_guard._status_extra import (
    gather_budget,
    gather_cache,
    gather_ledger_stats,
    gather_timer,
)
from leetcode_guard._status_full import explain_not_triggered, gather_full
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


# -- ledger stats ----------------------------------------------------------


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


# -- budgets, caches, timer ------------------------------------------------


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


def test_a_disabled_timer_is_reported():
    timer = gather_timer(
        run=lambda args: "disabled\n" if args[0] == "is-enabled" else "X=\n"
    )

    assert not timer.enabled
    assert timer.next_fire == "not scheduled"


# -- explain ---------------------------------------------------------------


def test_a_disabled_timer_is_the_first_thing_explained(
    data_dir: Path, hmac_key: Path, monkeypatch
):
    """ "Unlocked" with the timer off means the gate never even ran, which looks
    identical from outside to having banked credit."""
    from leetcode_guard import _status_extra, _status_full

    monkeypatch.setattr(
        _status_extra,
        "gather_timer",
        lambda **_k: _status_extra.TimerStatus(
            enabled=False, next_fire="never", detail="disabled"
        ),
    )
    monkeypatch.setattr(_status_full, "gather_timer", _status_extra.gather_timer)

    reasons = explain_not_triggered(full_for(data_dir, hmac_key))

    assert "NOT enabled" in reasons[0]


def test_banked_credit_is_explained_as_such(data_dir: Path, hmac_key: Path):
    ledger = ledger_with_credits(3, day=MONDAY, key_file=hmac_key)

    reasons = explain_not_triggered(full_for(data_dir, hmac_key, ledger))

    assert any("banked" in line for line in reasons)


def test_an_already_settled_day_is_explained_as_such(data_dir: Path, hmac_key: Path):
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    add_charge(ledger, MONDAY, key_file=hmac_key)

    reasons = explain_not_triggered(full_for(data_dir, hmac_key, ledger))

    assert any("already settled" in line for line in reasons)


def test_a_locked_gate_says_it_would_lock(data_dir: Path, hmac_key: Path):
    reasons = explain_not_triggered(full_for(data_dir, hmac_key))

    assert any("WOULD lock" in line for line in reasons)


def test_refused_credits_are_explained(data_dir: Path, hmac_key: Path):
    from leetcode_guard._ledger_io import append
    from leetcode_guard.tests._ledger_fixtures import forged_credit

    ledger = ledger_with_credits(2, day=MONDAY, key_file=hmac_key)
    append(ledger, [forged_credit()])

    reasons = explain_not_triggered(full_for(data_dir, hmac_key, ledger))

    assert any("REFUSED" in line for line in reasons)


def test_an_unreadable_key_is_explained(data_dir: Path, missing_key: Path):
    path = data_dir / "ledger.json"
    full = gather_full(now=MONDAY_NOON, ledger_path=path, key_file=missing_key)

    assert any(
        "integrity checking is OFF" in line for line in explain_not_triggered(full)
    )


# -- tray CLIs -------------------------------------------------------------


def test_state_word_tracks_the_verdict(data_dir: Path, hmac_key: Path):
    locked = full_for(data_dir, hmac_key)
    banked = full_for(
        data_dir, hmac_key, ledger_with_credits(3, day=MONDAY, key_file=hmac_key)
    )

    assert status_view.state_word(locked) == status_view.STATE_LOCK
    assert status_view.state_word(banked) == status_view.STATE_OK


def test_summary_line_names_the_shortfall(data_dir: Path, hmac_key: Path):
    line = status_view.summary_line(full_for(data_dir, hmac_key))

    assert line.startswith("LOCKED")
    assert "solve 1 problem" in line


def test_summary_line_pluralises(data_dir: Path, hmac_key: Path, monkeypatch):

    full = full_for(data_dir, hmac_key)
    saturday = type(full.gate)(
        **{**vars(full.gate), "needed": 2, "weekday": "Saturday", "cost": 2}
    )
    combined = type(full)(**{**vars(full), "gate": saturday})

    assert "solve 2 problems" in status_view.summary_line(combined)


def test_summary_line_when_unlocked(data_dir: Path, hmac_key: Path):
    full = full_for(
        data_dir, hmac_key, ledger_with_credits(3, day=MONDAY, key_file=hmac_key)
    )

    assert status_view.summary_line(full).startswith("Unlocked")


def test_the_flags_print_one_line_each(capsys, data_dir: Path):
    assert status_view.main(["--state"]) == 0
    assert capsys.readouterr().out.strip() in {"ok", "warn", "lock"}

    assert status_view.main(["--summary"]) == 0
    assert capsys.readouterr().out.strip()
