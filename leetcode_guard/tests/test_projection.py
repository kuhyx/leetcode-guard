"""The projection arithmetic, checked against hand-worked calendars."""

from __future__ import annotations

from datetime import date

import pytest

from leetcode_guard._progress import Progress
from leetcode_guard._projection import (
    Position,
    default_target,
    format_target,
    parse_target,
    percent,
    project,
)

SAT = date(2026, 9, 19)
"""The Saturday this was built on: Sun 20 + Mon-Fri + Sat 26 = 2+5+2 = 9."""


def never_free(_day):
    return False


def progress(easy=55, medium=0, hard=0) -> Progress:
    return Progress(
        solved={"Easy": easy, "Medium": medium, "Hard": hard},
        total={"Easy": 965, "Medium": 2115, "Hard": 975},
        fetched_at=0.0,
    )


def position(*, charged_today=True, available=0, debt=14) -> Position:
    return Position(
        today=SAT,
        charged_today=charged_today,
        available=available,
        debt_outstanding=debt,
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("26.09.2026", date(2026, 9, 26)),
        (" 26.09.2026 ", date(2026, 9, 26)),
        ("1.9.2026", date(2026, 9, 1)),
        ("2026-09-26", date(2026, 9, 26)),
        ("31.02.2026", None),
        ("26/09/2026", None),
        ("banana", None),
        ("", None),
    ],
)
def test_parse_target_reads_dotted_and_iso_dates(text, expected):
    assert parse_target(text) == expected


def test_the_default_target_is_new_years_eve_in_dotted_form():
    assert default_target(SAT) == date(2026, 12, 31)
    assert format_target(default_target(SAT)) == "31.12.2026"


def test_a_week_ahead_from_a_settled_saturday():
    """The worked example: 9 base + 14 debt - 0 banked = 23, rules collect 16."""
    result = project(
        date(2026, 9, 26), position(), is_free=never_free, progress=progress()
    )

    assert result.first_day == date(2026, 9, 20)
    assert (result.gated_days, result.free_days, result.base_cost) == (7, 0, 9)
    assert result.required == 23
    assert result.rules_demand == 16
    assert result.debt_left_by_rules == 7
    assert result.projected == {"Easy": 78, "Medium": 0, "Hard": 0}


def test_an_unsettled_today_is_counted_and_costs_the_weekend_price():
    result = project(
        SAT, position(charged_today=False), is_free=never_free, progress=None
    )

    assert result.first_day == SAT
    assert (result.gated_days, result.base_cost) == (1, 2)
    assert result.required == 2 + 14
    assert result.projected is None


def test_a_settled_today_asked_about_today_counts_no_days():
    result = project(SAT, position(), is_free=never_free, progress=None)

    assert (result.gated_days, result.base_cost, result.required) == (0, 0, 14)
    assert result.rules_demand == 0
    assert result.debt_left_by_rules == 14


def test_free_days_cost_nothing_and_repay_nothing():
    free = {date(2026, 9, 21), date(2026, 9, 22)}

    result = project(
        date(2026, 9, 26), position(), is_free=free.__contains__, progress=None
    )

    assert (result.gated_days, result.free_days, result.base_cost) == (5, 2, 7)
    assert result.rules_demand == 7 + 5
    assert result.debt_left_by_rules == 9


def test_banked_credits_reduce_the_demand_and_it_floors_at_zero():
    result = project(
        date(2026, 9, 20),
        position(available=50, debt=0),
        is_free=never_free,
        progress=None,
    )

    assert result.required == 0
    assert result.rules_demand == 0


def test_a_long_horizon_repays_the_whole_debt_under_the_rules():
    result = project(date(2026, 12, 31), position(), is_free=never_free, progress=None)

    assert result.gated_days == 103
    assert result.debt_left_by_rules == 0
    assert result.rules_demand == result.required


def test_new_solves_fill_easy_then_medium_then_hard():
    nearly_done = Progress(
        solved={"Easy": 963, "Medium": 2114, "Hard": 970},
        total={"Easy": 965, "Medium": 2115, "Hard": 975},
        fetched_at=0.0,
    )

    result = project(
        date(2026, 9, 26), position(debt=0), is_free=never_free, progress=nearly_done
    )

    # 9 required: 2 finish Easy, 1 finishes Medium, 5 land on Hard, 1 spills
    # past the end of the site and is dropped rather than invented.
    assert result.required == 9
    assert result.projected == {"Easy": 965, "Medium": 2115, "Hard": 975}


def test_percent_is_zero_over_an_empty_total():
    assert percent(3, 0) == 0.0
    assert percent(1, 4) == 25.0
