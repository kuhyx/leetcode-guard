"""A focus project switches the gate off exactly like a sick day: no price, no
charge, no debt, no lock -- and fails closed when ``focus_project`` is missing."""

from __future__ import annotations

from datetime import date, timedelta
import logging
import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
import sickdays

from leetcode_guard import _focus, _gate_today, _sick
from leetcode_guard import _glyphs as g
from leetcode_guard._debt import compute_debt, cost_phrase

# Imported directly so the names keep the real functions: the autouse stub
# replaces the module attributes per test.
from leetcode_guard._focus import project_name as real_project_name
from leetcode_guard._focus import stands_down as real_stands_down
from leetcode_guard._gate import DayContext, GateState
from leetcode_guard._ledger_io import Ledger
from leetcode_guard._status import format_status, gather_status
from leetcode_guard._status_full import explain_not_triggered
from leetcode_guard._status_projection import _is_off_day
from leetcode_guard.tests._gate_fixtures import decide_with, view_of
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    NOW,
    SATURDAY,
    TUESDAY,
    WEDNESDAY,
)
from leetcode_guard.tests.test_projection import never_free
from leetcode_guard.tests.test_status_gather import full_for

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

NEXT_MONDAY = MONDAY + timedelta(days=7)


@pytest.fixture(name="focus_on")
def fixture_focus_on(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., list[tuple[str, date]]]:
    """Declare focus days; returns the (gate, day) questions asked."""
    asked: list[tuple[str, date]] = []

    def declare(*days: date) -> list[tuple[str, date]]:
        def stands_down(gate: str, day: date) -> bool:
            asked.append((gate, day))
            return day in days

        monkeypatch.setattr(_focus, "stands_down", stands_down)
        return asked

    return declare


def stands_down_on(*days: date):
    """Build a ``sickdays.stands_down`` stub that is true on ``days`` only."""
    return lambda _locker, day=None, **_kw: day in days


def test_a_focus_day_is_a_stand_down_day(focus_on):
    """A declared focus day stands the leetcode gate down, other days do not."""
    asked = focus_on(MONDAY)

    assert _sick.leetcode_stands_down(MONDAY) is True
    assert _sick.leetcode_stands_down(WEDNESDAY) is False
    assert {gate for gate, _day in asked} == {"leetcode"}


def test_a_sick_day_still_stands_down_without_focus(monkeypatch):
    """A sick day still stands the gate down when no focus project is active."""
    monkeypatch.setattr(sickdays, "stands_down", lambda *_a, **_k: True)

    assert _sick.leetcode_stands_down(MONDAY) is True


def test_a_focus_day_adds_nothing_to_the_debt(focus_on):
    """Focus days are left out of the missed days, so the debt owed shrinks."""
    plain = compute_debt(Ledger(), day=NEXT_MONDAY, is_free=never_free, start=MONDAY)
    focus_on(MONDAY, SATURDAY)
    focused = compute_debt(
        Ledger(),
        day=NEXT_MONDAY,
        is_free=never_free,
        is_sick=_sick.leetcode_stands_down,
        start=MONDAY,
    )

    assert plain.missed_days - focused.missed_days == 2
    assert plain.owed > focused.owed


def test_decide_today_on_a_focus_day_charges_and_locks_nothing(focus_on, debt_starts):
    """On a focus day the gate is unlocked with no charge, no need and no debt."""
    debt_starts(MONDAY)
    focus_on(MONDAY, TUESDAY, WEDNESDAY)

    decision = _gate_today.decide_today(Ledger(), day=WEDNESDAY, now=NOW)

    assert decision.state is GateState.UNLOCKED_FOCUS_DAY
    assert (decision.locked, decision.charge, decision.needed) == (False, None, 0)
    assert decision.debt.missed_days == 0
    assert _gate_today.gate_off(WEDNESDAY) is True


def test_the_status_projection_skips_focus_days(focus_on):
    """The status projection treats a focus day as an off day."""
    focus_on(SATURDAY)

    assert _is_off_day(SATURDAY) is True
    assert _is_off_day(MONDAY) is False


def test_no_focus_day_by_default():
    """With no project declared, no day is a focus day."""
    assert _focus.stands_down("leetcode", MONDAY) is False


def test_stands_down_asks_the_package(monkeypatch):
    """``stands_down`` returns what the ``focus_project`` package answers."""
    fake = SimpleNamespace(stands_down=lambda gate, day: (gate, day) == ("x", MONDAY))
    monkeypatch.setitem(sys.modules, "focus_project", fake)

    assert real_stands_down("x", MONDAY) is True
    assert real_stands_down("x", NEXT_MONDAY) is False


def test_a_missing_package_fails_closed_and_logs_once(monkeypatch, caplog):
    """Without ``focus_project`` no day stands down and one error is logged."""
    monkeypatch.setitem(sys.modules, "focus_project", None)
    monkeypatch.setattr(_focus, "_warned", set())

    with caplog.at_level(logging.ERROR, logger=_focus.__name__):
        assert real_stands_down("leetcode", MONDAY) is False
        assert real_stands_down("leetcode", WEDNESDAY) is False

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "focus_project is not importable" in errors[0].getMessage()


def test_a_focus_day_says_focus_not_sick(focus_on, debt_starts):
    """A focus day reports the focus-day state and names the project."""
    debt_starts(MONDAY)
    focus_on(WEDNESDAY)

    decision = _gate_today.decide_today(Ledger(), day=WEDNESDAY, now=NOW)

    assert decision.state is GateState.UNLOCKED_FOCUS_DAY
    assert decision.state.value == "focus-day"
    assert decision.reason == "focus day: Test project"
    assert not decision.locked


def test_a_focus_day_costs_nothing_even_with_debt(focus_on, debt_starts):
    """Outstanding debt still makes a focus day cost 0."""
    debt_starts(MONDAY)
    plain = _gate_today.decide_today(Ledger(), day=WEDNESDAY, now=NOW)
    focus_on(TUESDAY, WEDNESDAY)

    decision = _gate_today.decide_today(Ledger(), day=WEDNESDAY, now=NOW)

    assert plain.cost > 0
    assert decision.cost == 0
    assert cost_phrase(WEDNESDAY, decision.cost, decision.debt) == "Wednesday costs 0"


def test_a_real_sick_day_keeps_its_text_when_focus_also_applies(
    focus_on, debt_starts, monkeypatch
):
    """A day that is both sick and focus keeps the sick-day state and reason."""
    debt_starts(MONDAY)
    focus_on(WEDNESDAY)
    monkeypatch.setattr(sickdays, "stands_down", stands_down_on(WEDNESDAY))

    decision = _gate_today.decide_today(Ledger(), day=WEDNESDAY, now=NOW)

    assert decision.state is GateState.UNLOCKED_SICK_DAY
    assert decision.reason == "today is a sick day"


def test_the_window_and_status_name_the_focus_day(
    monkeypatch, hmac_key: Path, data_dir: Path
):
    """The window headline, status text and explanation all name the focus day."""
    monkeypatch.setattr(_focus, "stands_down", lambda *_a, **_k: True)
    decision = decide_with(Ledger(), hmac_key, DayContext(focus_day="Prep"))
    model = view_of(decision)
    snapshot = gather_status(ledger_path=data_dir / "ledger.json", key_file=hmac_key)
    lines = explain_not_triggered(full_for(data_dir, hmac_key, Ledger()))

    assert model.headline == g.FOCUS
    assert "day        " in format_status(snapshot)
    assert "costs 0" in format_status(snapshot)
    assert "focus-day -- focus day: Test project" in format_status(snapshot)
    assert any("focus day" in line for line in lines)


def test_the_project_name_comes_from_the_package(monkeypatch):
    """The project name comes from the package, with a fallback when absent."""
    project = SimpleNamespace(name="HackerRank prep")
    fake = SimpleNamespace(active=lambda day: project if day == MONDAY else None)
    monkeypatch.setitem(sys.modules, "focus_project", fake)

    assert real_project_name(MONDAY) == "HackerRank prep"
    assert real_project_name(WEDNESDAY) == "focus project"
    monkeypatch.setitem(sys.modules, "focus_project", None)
    assert real_project_name(MONDAY) == "focus project"
