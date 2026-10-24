"""``gate_off``: the live "does this gate stand down today?" fact (2026-10-24).

The bonus for a LeetCode day needs the day paid in full (earned_time 0.18.0);
on a day with no price -- free, or sick without keeping ``leetcode`` -- one
verified solve still earns, and the consumer has to ask that live. The
endpoint publishes it as a fact beside ``solved_today``; it is never ledger
state, so clearing a sick day takes the exception back at once.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import freedays
import pytest
import sickdays

from leetcode_guard import _gate_today
from leetcode_guard._web_server import build_status_payload
from leetcode_guard.solved_today import SolvedToday
from leetcode_guard.tests.test_sick_keep import (
    KEEP_LEETCODE,
    KEEP_NOTHING,
    sick_with,
)

SAT = date(2026, 10, 24)


def _free_on(monkeypatch: pytest.MonkeyPatch, *days: date) -> None:
    monkeypatch.setattr(freedays, "is_free_day", lambda day, **_kw: day in days)


def test_an_ordinary_day_has_the_gate_on(monkeypatch: pytest.MonkeyPatch) -> None:
    _free_on(monkeypatch)
    sick_with(monkeypatch, {})
    assert _gate_today.gate_off(SAT) is False


def test_a_free_day_has_the_gate_off(monkeypatch: pytest.MonkeyPatch) -> None:
    _free_on(monkeypatch, SAT)
    sick_with(monkeypatch, {})
    assert _gate_today.gate_off(SAT) is True


def test_a_sick_day_keeping_nothing_has_the_gate_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _free_on(monkeypatch)
    sick_with(monkeypatch, {SAT: KEEP_NOTHING})
    assert _gate_today.gate_off(SAT) is True


def test_a_sick_day_keeping_leetcode_has_the_gate_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _free_on(monkeypatch)
    sick_with(monkeypatch, {SAT: KEEP_LEETCODE})
    assert _gate_today.gate_off(SAT) is False
    assert sickdays.is_sick_day(SAT) is True


@pytest.mark.parametrize("off", [True, False])
def test_the_endpoint_publishes_it(off: bool) -> None:
    answer = SolvedToday(checked=True, solved=True, count=1, reason="1 today")
    with (
        patch("leetcode_guard._web_server.solved_today", return_value=answer),
        patch("leetcode_guard._web_server.gate_off", return_value=off),
    ):
        payload = build_status_payload()
    assert payload["leetcode"]["gate_off"] is off
