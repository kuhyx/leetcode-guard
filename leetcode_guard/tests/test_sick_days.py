"""Sick days: the gate stands down, the debt is untouched, and sick != free."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import TYPE_CHECKING

import pytest
import sickdays

from leetcode_guard import _gate_today, _status_projection
from leetcode_guard import _glyphs as g
from leetcode_guard._daycost import day_cost
from leetcode_guard._debt import compute_debt
from leetcode_guard._gate import DayContext, GateState, decide
from leetcode_guard._ledger_entries import charge_entry
from leetcode_guard._ledger_io import Ledger, append
from leetcode_guard._projection import project
from leetcode_guard._projection_text import projection_lines
from leetcode_guard._status import gather_status
from leetcode_guard._status_full import explain_not_triggered
from leetcode_guard._status_projection import _is_off_day
from leetcode_guard.tests._gate_fixtures import decide_with, view_of
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    NOW,
    SATURDAY,
    TUESDAY,
    WEDNESDAY,
    add_charge,
    ledger_with_credits,
)
from leetcode_guard.tests.test_projection import SAT, never_free, position, progress
from leetcode_guard.tests.test_status_gather import full_for

if TYPE_CHECKING:
    from pathlib import Path


NEXT_MONDAY = MONDAY + timedelta(days=7)


def sick_on(*days: date):
    """A sick-day predicate that is true on exactly these days."""
    return lambda day: day in days


def stands_down_on(*days: date):
    """A fake ``sickdays.stands_down``: these days are sick, keeping nothing."""
    return lambda _locker, day=None, **_kw: day in days


def test_a_sick_day_stands_down_with_no_credit_and_no_charge(hmac_key: Path):
    """A sick day unlocks with nothing needed and no charge written."""
    decision = decide_with(Ledger(), hmac_key, DayContext(sick_day=True))

    assert decision.state is GateState.UNLOCKED_SICK_DAY
    assert decision.state.value == "sick-day"
    assert not decision.locked
    assert decision.charge is None
    assert decision.needed == 0


def test_sick_is_not_free(hmac_key: Path):
    """A sick day reports its own state, distinct from a free day."""
    free = decide_with(Ledger(), hmac_key, DayContext(free_day=True))
    sick = decide_with(Ledger(), hmac_key, DayContext(sick_day=True))

    assert free.state is GateState.UNLOCKED_FREE_DAY
    assert sick.state is not free.state


def test_a_sick_day_does_not_override_an_untrusted_clock(hmac_key: Path):
    """A clock that moved backwards still locks even on a sick day."""
    ledger = Ledger()
    add_charge(ledger, TUESDAY, key_file=hmac_key)

    decision = decide_with(ledger, hmac_key, DayContext(sick_day=True))

    assert decision.state is GateState.LOCKED_CLOCK_UNTRUSTED


def test_a_workday_penalty_is_ignored_on_a_sick_day(hmac_key: Path):
    """The workday penalty doubles the cost only on a non-sick day."""
    kwargs = {"day": TUESDAY, "now": NOW, "key_file": hmac_key}
    penalised = DayContext(workday_penalty=True)
    sick = DayContext(workday_penalty=True, sick_day=True)

    assert decide(Ledger(), context=penalised, **kwargs).cost == 2
    assert decide(Ledger(), context=sick, **kwargs).cost == 1


def test_a_sick_day_adds_nothing_to_the_debt():
    """Missed sick days are not owed and not counted as missed."""
    plain = compute_debt(Ledger(), day=NEXT_MONDAY, is_free=never_free, start=MONDAY)
    sick = compute_debt(
        Ledger(),
        day=NEXT_MONDAY,
        is_free=never_free,
        is_sick=sick_on(MONDAY, SATURDAY),
        start=MONDAY,
    )

    assert plain.owed - sick.owed == day_cost(MONDAY) + day_cost(SATURDAY)
    assert plain.missed_days - sick.missed_days == 2


def test_a_charge_on_a_sick_day_repays_by_the_ordinary_rule(hmac_key: Path):
    """A surcharged charge repays one whether or not its day was sick."""
    ledger = Ledger()
    append(ledger, [charge_entry(MONDAY, now=NOW, key_file=hmac_key, surcharge=1)])

    for sick in (sick_on(), sick_on(MONDAY)):
        debt = compute_debt(
            ledger,
            day=WEDNESDAY,
            is_free=never_free,
            is_sick=sick,
            start=MONDAY - timedelta(days=3),
        )
        assert debt.repaid == 1


@pytest.mark.usefixtures("hmac_key")
def test_decide_today_reads_the_sick_pool(debt_starts, monkeypatch):
    """decide_today consults sickdays for both the debt and today's state."""
    debt_starts(MONDAY)
    monkeypatch.setattr(sickdays, "stands_down", stands_down_on(MONDAY, TUESDAY))

    sick = _gate_today.decide_today(Ledger(), day=WEDNESDAY, now=NOW)
    on_the_day = _gate_today.decide_today(Ledger(), day=TUESDAY, now=NOW)

    assert sick.debt.missed_days == 0
    assert on_the_day.state is GateState.UNLOCKED_SICK_DAY


def test_decide_today_reads_the_real_pool_file():
    """A sick day written to the real pool file unlocks today."""
    today = date.today()
    sickdays.add_sick_day(today, is_free=lambda _day: False)

    decision = _gate_today.decide_today(Ledger(), day=today, now=NOW)

    assert decision.state is GateState.UNLOCKED_SICK_DAY


def test_the_projection_counts_sick_days_apart_from_free():
    """The projection counts sick days separately and drops them from gated days."""
    sick = sick_on(date(2026, 9, 21), date(2026, 9, 22))
    result = project(
        date(2026, 9, 26),
        replace(position(), is_sick=sick),
        is_free=never_free,
        progress=progress(),
    )
    plain = project(
        date(2026, 9, 26), position(), is_free=never_free, progress=progress()
    )

    assert (result.sick_days, result.free_days, plain.sick_days) == (2, 0, 0)
    assert result.gated_days == plain.gated_days - 2
    assert result.base_cost < plain.base_cost
    assert "5 gated day(s), 0 free, 2 sick." in projection_lines(result, None)[0]
    assert ", 0 sick" not in projection_lines(plain, None)[0]


def test_sick_days_reach_the_status_projection(
    data_dir: Path, hmac_key: Path, monkeypatch
):
    """The status projection treats sick days as off days, not gated or free."""
    snapshot = gather_status(ledger_path=data_dir / "ledger.json", key_file=hmac_key)
    monkeypatch.setattr(sickdays, "stands_down", lambda *_a, **_k: True)

    report = _status_projection.build_report(
        snapshot, None, _status_projection.ProjectionInputs("31.12.2999")
    )

    assert report.projection is not None
    assert report.projection.gated_days == 0
    assert report.projection.free_days == 0
    assert _is_off_day(SAT)


def test_the_window_says_sick_not_unlocked(hmac_key: Path):
    """The view headline names a sick day rather than a free unlock."""
    decision = decide_with(Ledger(), hmac_key, DayContext(sick_day=True))

    model = view_of(decision)

    assert model.headline == g.SICK
    assert model.headline != g.SOLVED


def test_status_explains_a_sick_day(data_dir: Path, hmac_key: Path, monkeypatch):
    """The status explanation mentions the sick day."""
    monkeypatch.setattr(sickdays, "stands_down", lambda *_a, **_k: True)
    ledger = ledger_with_credits(0, day=MONDAY, key_file=hmac_key)

    lines = explain_not_triggered(full_for(data_dir, hmac_key, ledger))

    assert any("sick day" in line for line in lines)
