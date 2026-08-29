"""Remaining status-view branches: explanations, sections and the tray CLIs.

Split from ``test_status_view.py`` for the repo's 400-line cap; that file
keeps the data-gathering tests, this one the rendering tests.

Tk is a MagicMock throughout, so these assert on *what was asked of Tk*. The
pixel check is the Xvfb screenshot -- which is how the clipped-text bug was
found, since no assertion could see a wraplength wider than its own window.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from leetcode_guard import status_view
from leetcode_guard._ledger_io import save_ledger
from leetcode_guard._status_full import explain_not_triggered, gather_full
from leetcode_guard._status_sections import render_sections
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    add_charge,
    ledger_with_credits,
)

if TYPE_CHECKING:
    from pathlib import Path

MONDAY_NOON = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


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


def test_tampered_and_unparsable_rows_are_reported(data_dir: Path, hmac_key: Path):
    from leetcode_guard._ledger_io import append
    from leetcode_guard.tests._ledger_fixtures import forged_credit

    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    append(ledger, [forged_credit()])
    reasons = explain_not_triggered(full_for(data_dir, hmac_key, ledger))

    assert any("failed their signature" in line for line in reasons)


def test_unreadable_rows_are_reported(data_dir: Path, hmac_key: Path):
    path = data_dir / "ledger.json"
    path.write_text('{"version": 1, "entries": [{"junk": 1}]}', encoding="utf-8")

    reasons = explain_not_triggered(
        gather_full(now=MONDAY_NOON, ledger_path=path, key_file=hmac_key)
    )

    assert any("could not be read" in line for line in reasons)


def test_an_untrusted_clock_is_reported(data_dir: Path, hmac_key: Path):
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    add_charge(ledger, MONDAY + timedelta(days=5), key_file=hmac_key)

    reasons = explain_not_triggered(full_for(data_dir, hmac_key, ledger))

    assert any("moved backwards" in line for line in reasons)


def test_the_not_started_reason_shows_once_the_gate_is_in_force(
    data_dir: Path, hmac_key: Path, monkeypatch
):
    """Belt and braces: the reason is suppressed only while the dedicated
    not-in-force line is already saying it."""
    full = full_for(data_dir, hmac_key)
    gate = type(full.gate)(
        **{
            **vars(full.gate),
            "state": "not-started",
            "locked": False,
            "reason": "custom reason",
        }
    )
    combined = type(full)(**{**vars(full), "gate": gate, "in_force": True})

    assert "custom reason" in explain_not_triggered(combined)


def test_sections_render_with_solves_and_settled_days(
    data_dir: Path, hmac_key: Path, tk_mock
):
    """Exercises the populated branches of the solve and settled-day lists."""
    ledger = ledger_with_credits(2, day=MONDAY, key_file=hmac_key)
    add_charge(ledger, MONDAY, key_file=hmac_key)

    render_sections(
        tk_mock.Frame(), status_view._COLORS, full_for(data_dir, hmac_key, ledger)
    )

    captions = [str(c.kwargs.get("text", "")) for c in tk_mock.Label.call_args_list]
    assert any("Most recent" in c for c in captions)
    assert any(MONDAY.isoformat() in c for c in captions)


def test_sections_render_suggestions_when_a_pool_is_cached(
    data_dir: Path, hmac_key: Path, tk_mock
):
    from leetcode_guard._pool_cache import CachedPool, write_cache
    from leetcode_guard._problem import parse_problem
    from leetcode_guard.tests._net_fixtures import problem_row

    problems = tuple(
        p
        for p in (parse_problem(problem_row(s)) for s in ("two-sum",))
        if p is not None
    )
    write_cache(
        data_dir / "pool_cache.json",
        CachedPool(
            problems=problems, fetched_at=MONDAY_NOON.timestamp(), complete=True
        ),
    )

    render_sections(tk_mock.Frame(), status_view._COLORS, full_for(data_dir, hmac_key))

    captions = [str(c.kwargs.get("text", "")) for c in tk_mock.Label.call_args_list]
    assert any("leetcode.com/problems/two-sum" in c for c in captions)


def test_an_exhausted_budget_is_flagged(data_dir: Path, hmac_key: Path, tk_mock):
    full = full_for(data_dir, hmac_key)
    spent = type(full.escape)(**{**vars(full.escape), "exhausted": True})
    combined = type(full)(**{**vars(full), "escape": spent})

    render_sections(tk_mock.Frame(), status_view._COLORS, combined)

    captions = [str(c.kwargs.get("text", "")) for c in tk_mock.Label.call_args_list]
    assert any("EXHAUSTED" in c for c in captions)


def test_the_verdict_is_green_amber_or_red(data_dir: Path, hmac_key: Path):
    from leetcode_guard._status_sections import _verdict_color

    colors = status_view._COLORS
    locked = full_for(data_dir, hmac_key)
    banked = full_for(
        data_dir, hmac_key, ledger_with_credits(3, day=MONDAY, key_file=hmac_key)
    )

    assert _verdict_color(colors, locked) == colors.danger
    assert _verdict_color(colors, banked) == colors.success


def test_the_window_can_be_refreshed(data_dir: Path, hmac_key: Path, tk_mock):
    refreshed: list[bool] = []
    window = status_view.StatusWindow(
        a_root(tk_mock),
        full_for(data_dir, hmac_key),
        on_refresh=lambda: refreshed.append(True),
        on_close=lambda: None,
    )

    window.render(full_for(data_dir, hmac_key))

    assert window.container is not None


def test_the_default_gather_reads_the_isolated_paths(data_dir: Path):
    full = gather_full()

    assert full.ledger_path.endswith("ledger.json")
    assert not full.sync_configured
    assert not full.cookies_configured


def test_the_summary_line_reports_a_gate_not_yet_in_force(
    data_dir: Path, hmac_key: Path
):
    full = full_for(data_dir, hmac_key)
    gate = type(full.gate)(
        **{
            **vars(full.gate),
            "state": "not-started",
            "locked": False,
            "reason": "not yet",
        }
    )
    combined = type(full)(**{**vars(full), "gate": gate})

    assert status_view.summary_line(combined) == "leetcode-guard: not yet"


def test_the_state_word_warns_with_nothing_banked(data_dir: Path, hmac_key: Path):
    full = full_for(data_dir, hmac_key)
    gate = type(full.gate)(**{**vars(full.gate), "locked": False, "available": 0})
    combined = type(full)(**{**vars(full), "gate": gate})

    assert status_view.state_word(combined) == status_view.STATE_WARN


def test_rerendering_clears_the_previous_widgets(
    data_dir: Path, hmac_key: Path, tk_mock
):
    """Otherwise every Refresh stacks a second copy of the whole panel."""
    root = a_root(tk_mock)
    window = status_view.StatusWindow(
        root,
        full_for(data_dir, hmac_key),
        on_refresh=lambda: None,
        on_close=lambda: None,
    )
    stale = tk_mock.Label()
    window.container.winfo_children.return_value = [stale]

    window.render(full_for(data_dir, hmac_key))

    stale.destroy.assert_called_once()
