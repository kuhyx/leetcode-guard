"""Tests for the status window itself -- widgets, wrapping and exits.

Split from ``test_status_view.py`` for the repo's 400-line cap; that file
keeps the data-gathering tests, this one the rendering tests.

Tk is a MagicMock throughout, so these assert on *what was asked of Tk*. The
pixel check is the Xvfb screenshot -- which is how the clipped-text bug was
found, since no assertion could see a wraplength wider than its own window.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from leetcode_guard import status_view
from leetcode_guard._ledger_io import save_ledger
from leetcode_guard._status_full import gather_full
from leetcode_guard._status_sections import DEFAULT_WRAP, render_sections
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
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


# -- window ----------------------------------------------------------------


def test_the_window_renders_every_section(data_dir: Path, hmac_key: Path, tk_mock):
    full = full_for(
        data_dir, hmac_key, ledger_with_credits(2, day=MONDAY, key_file=hmac_key)
    )
    closed: list[bool] = []

    window = status_view.StatusWindow(
        a_root(tk_mock),
        full,
        on_refresh=lambda: None,
        on_close=lambda: closed.append(True),
    )

    captions = [
        str(call.kwargs.get("text", "")) for call in tk_mock.Label.call_args_list
    ]
    for expected in (
        "Right now",
        "Why the lock did not trigger",
        "Credits (tokens)",
        "Solves",
        "Days settled",
        "Escape budgets",
        "Ledger integrity",
        "Scheduling and caches",
        "Suggested problems",
    ):
        assert any(expected in caption for caption in captions), expected
    assert window.container is not None


def test_the_window_offers_a_close_button(data_dir: Path, hmac_key: Path, tk_mock):
    """Emphatically required: a status panel you cannot dismiss is its own bug."""
    status_view.StatusWindow(
        a_root(tk_mock),
        full_for(data_dir, hmac_key),
        on_refresh=lambda: None,
        on_close=lambda: None,
    )

    labels = [
        str(call.kwargs.get("text", "")) for call in tk_mock.Button.call_args_list
    ]
    assert any("Close" in label for label in labels)
    assert any("Refresh" in label for label in labels)


def test_the_wrap_width_falls_back_before_the_window_is_mapped(
    data_dir: Path, hmac_key: Path, tk_mock
):
    """`winfo_width` reports 1 until the window is mapped; wrapping at that
    would make every line one character wide."""
    root = a_root(tk_mock, width=1)

    window = status_view.StatusWindow(
        root,
        full_for(data_dir, hmac_key),
        on_refresh=lambda: None,
        on_close=lambda: None,
    )

    assert window._wrap_width() == DEFAULT_WRAP


def test_the_wrap_width_follows_a_real_window(data_dir: Path, hmac_key: Path, tk_mock):
    root = a_root(tk_mock, width=1200)

    window = status_view.StatusWindow(
        root,
        full_for(data_dir, hmac_key),
        on_refresh=lambda: None,
        on_close=lambda: None,
    )

    assert window._wrap_width() == 1200 - status_view._WRAP_MARGIN


def test_render_sections_clamps_a_silly_wrap(data_dir: Path, hmac_key: Path, tk_mock):
    render_sections(
        tk_mock.Frame(), status_view._COLORS, full_for(data_dir, hmac_key), wrap=10
    )

    wraps = [
        call.kwargs.get("wraplength")
        for call in tk_mock.Label.call_args_list
        if "wraplength" in call.kwargs
    ]
    assert wraps
    assert all(value >= 320 for value in wraps)
