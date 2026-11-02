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
from leetcode_guard._debt import compute_debt
from leetcode_guard._gate import GateState
from leetcode_guard._ledger_io import Ledger
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    NOW,
    SATURDAY,
    TUESDAY,
    WEDNESDAY,
)
from leetcode_guard.tests.test_projection import never_free

if TYPE_CHECKING:
    from collections.abc import Callable

NEXT_MONDAY = MONDAY + timedelta(days=7)
REAL_STANDS_DOWN = _focus.stands_down
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

    assert decision.state is GateState.UNLOCKED_SICK_DAY
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
