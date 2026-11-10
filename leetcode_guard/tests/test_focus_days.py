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

from leetcode_guard import _focus, _gate_today, _sick, _status_projection
from leetcode_guard import _glyphs as g
from leetcode_guard._debt import compute_debt, cost_phrase
from leetcode_guard._gate import DayContext, GateState, decide
from leetcode_guard._ledger_io import Ledger
from leetcode_guard._status_full import explain_not_triggered
from leetcode_guard._viewmodel import build_viewmodel
from leetcode_guard._viewmodel_source import ViewSource
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    NOW,
    SATURDAY,
    TUESDAY,
    WEDNESDAY,
)
from leetcode_guard.tests.test_projection import never_free
from leetcode_guard.tests.test_status_gather import full_for
from leetcode_guard.tests.test_viewmodel import (
    CHECKED_AT,
    OK_PROBE,
    SIGNED_OUT,
    pool_of,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

NEXT_MONDAY = MONDAY + timedelta(days=7)
REAL_STANDS_DOWN = _focus.stands_down
REAL_PROJECT_NAME = _focus.project_name
"""Captured at import: the autouse stub replaces the module attribute per test."""


@pytest.fixture
def focus_on(monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[tuple[str, date]]]:
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
    return lambda _locker, day=None, **_kw: day in days


def test_a_focus_day_is_a_stand_down_day(focus_on):
    asked = focus_on(MONDAY)

    assert _sick.leetcode_stands_down(MONDAY) is True
    assert _sick.leetcode_stands_down(WEDNESDAY) is False
    assert {gate for gate, _day in asked} == {"leetcode"}


def test_a_sick_day_still_stands_down_without_focus(monkeypatch):
    monkeypatch.setattr(sickdays, "stands_down", lambda *_a, **_k: True)

    assert _sick.leetcode_stands_down(MONDAY) is True


def test_a_focus_day_adds_nothing_to_the_debt(focus_on):
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
    debt_starts(MONDAY)
    focus_on(MONDAY, TUESDAY, WEDNESDAY)

    decision = _gate_today.decide_today(Ledger(), day=WEDNESDAY, now=NOW)

    assert decision.state is GateState.UNLOCKED_FOCUS_DAY
    assert (decision.locked, decision.charge, decision.needed) == (False, None, 0)
    assert decision.debt.missed_days == 0
    assert _gate_today.gate_off(WEDNESDAY) is True


def test_the_status_projection_skips_focus_days(focus_on):
    focus_on(SATURDAY)

    assert _status_projection._is_off_day(SATURDAY) is True
    assert _status_projection._is_off_day(MONDAY) is False


def test_no_focus_day_by_default():
    assert _focus.stands_down("leetcode", MONDAY) is False


def test_stands_down_asks_the_package(monkeypatch):
    fake = SimpleNamespace(stands_down=lambda gate, day: (gate, day) == ("x", MONDAY))
    monkeypatch.setitem(sys.modules, "focus_project", fake)

    assert REAL_STANDS_DOWN("x", MONDAY) is True
    assert REAL_STANDS_DOWN("x", NEXT_MONDAY) is False


def test_a_missing_package_fails_closed_and_logs_once(monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, "focus_project", None)
    monkeypatch.setattr(_focus, "_warned", set())

    with caplog.at_level(logging.ERROR, logger=_focus.__name__):
        assert REAL_STANDS_DOWN("leetcode", MONDAY) is False
        assert REAL_STANDS_DOWN("leetcode", WEDNESDAY) is False

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "focus_project is not importable" in errors[0].getMessage()


def test_a_focus_day_says_focus_not_sick(focus_on, debt_starts):
    debt_starts(MONDAY)
    focus_on(WEDNESDAY)

    decision = _gate_today.decide_today(Ledger(), day=WEDNESDAY, now=NOW)

    assert decision.state is GateState.UNLOCKED_FOCUS_DAY
    assert decision.state.value == "focus-day"
    assert decision.reason == "focus day: Test project"
    assert not decision.locked


def test_a_focus_day_costs_nothing_even_with_debt(focus_on, debt_starts):
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
    debt_starts(MONDAY)
    focus_on(WEDNESDAY)
    monkeypatch.setattr(sickdays, "stands_down", stands_down_on(WEDNESDAY))

    decision = _gate_today.decide_today(Ledger(), day=WEDNESDAY, now=NOW)

    assert decision.state is GateState.UNLOCKED_SICK_DAY
    assert decision.reason == "today is a sick day"


def test_the_window_and_status_name_the_focus_day(
    monkeypatch, hmac_key: Path, data_dir: Path
):
    from leetcode_guard._status import format_status, gather_status

    monkeypatch.setattr(_focus, "stands_down", lambda *_a, **_k: True)
    decision = decide(
        Ledger(),
        day=MONDAY,
        now=NOW,
        key_file=hmac_key,
        context=DayContext(focus_day="Prep"),
    )
    model = build_viewmodel(
        decision,
        ViewSource(pool_of(), SIGNED_OUT, limit=10),
        OK_PROBE,
        checked_at=CHECKED_AT,
    )
    snapshot = gather_status(ledger_path=data_dir / "ledger.json", key_file=hmac_key)
    lines = explain_not_triggered(full_for(data_dir, hmac_key, Ledger()))

    assert model.headline == g.FOCUS
    assert "day        " in format_status(snapshot)
    assert "costs 0" in format_status(snapshot)
    assert "focus-day -- focus day: Test project" in format_status(snapshot)
    assert any("focus day" in line for line in lines)


def test_the_project_name_comes_from_the_package(monkeypatch):
    project = SimpleNamespace(name="HackerRank prep")
    fake = SimpleNamespace(active=lambda day: project if day == MONDAY else None)
    monkeypatch.setitem(sys.modules, "focus_project", fake)

    assert REAL_PROJECT_NAME(MONDAY) == "HackerRank prep"
    assert REAL_PROJECT_NAME(WEDNESDAY) == "focus project"
    monkeypatch.setitem(sys.modules, "focus_project", None)
    assert REAL_PROJECT_NAME(MONDAY) == "focus project"
