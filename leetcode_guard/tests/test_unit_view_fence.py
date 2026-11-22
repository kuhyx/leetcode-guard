"""The unit view never raises into the lock, and reads the day on every repaint."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from leetcode_guard import _unit_view
from leetcode_guard._phase import PhaseState
from leetcode_guard._phase_file import write_phase
from leetcode_guard._unit_view import unit_view, view_now
from leetcode_guard.tests._theory_scenario import states, taught, world
from leetcode_guard.tests.test_unit_view import DAY, NOW

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def boom(*_args: object, **_kwargs: object) -> None:
    """A reader with a bug."""
    raise RuntimeError


def test_a_bug_in_the_live_read_is_logged_and_holds_the_signed_phase(
    tmp_path, monkeypatch, caplog, data_dir: Path, hmac_key: Path
):
    """Never raises into the lock: a crash costs the counts, never the window."""
    world(tmp_path, monkeypatch)
    held = PhaseState(unit="b", phase="solve")
    write_phase(held, day=DAY, now=NOW, key_file=hmac_key)

    monkeypatch.setattr(_unit_view, "gather_phase", boom)
    with caplog.at_level(logging.WARNING):
        shown = view_now(data_dir / "ledger.json", day=DAY, key_file=hmac_key)

    assert (shown.unit, shown.phase, shown.cards_total) == ("b", "solve", None)
    assert any(r.exc_info for r in caplog.records)


def test_a_bug_in_the_held_read_too_falls_back_to_none(
    monkeypatch, caplog, data_dir: Path, hmac_key: Path
):
    """Both reads crash: still a view, phase "none" (today's list), logged."""
    monkeypatch.setattr(_unit_view, "gather_phase", boom)
    monkeypatch.setattr(_unit_view, "read_phase", boom)
    with caplog.at_level(logging.WARNING):
        shown = view_now(data_dir / "ledger.json", day=DAY, key_file=hmac_key)

    assert (shown.unit, shown.phase) == ("", "none")
    assert len([r for r in caplog.records if r.exc_info]) == 2


def test_the_day_is_read_on_every_repaint(
    tmp_path, monkeypatch: pytest.MonkeyPatch, data_dir: Path, hmac_key: Path
):
    """A lock left open past midnight counts the new day's minutes."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    taught(hmac_key, NOW, ("a", 30))
    days = iter([DAY, DAY.replace(day=DAY.day + 1)])
    repaint = unit_view(
        data_dir / "ledger.json", key_file=hmac_key, today=lambda: next(days)
    )

    assert repaint().theory_minutes_today == 30
    assert repaint().theory_minutes_today == 0
