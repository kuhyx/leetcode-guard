"""The what-if arithmetic, pinned to the question that created it.

Asked 2026-09-20: "by how much do I raise the Tue-Thu price to have solved all
837 free Easy problems by 31.12.2027?" -- from 58 solved, 13 credits of debt,
nothing banked. Worked by hand first: 21.09.2026-06.10.2026 is fixed at 25
(the interim prices); 07.10.2026-31.12.2027 is 451 days, 64 of each weekday
plus an extra Wed/Thu/Fri, so it costs 579 * price + 129 (the flat 1 on 129
Mon/Fri days). Price 1 forces 733 + 13 = 746 of the 779 needed and lands on
21.01.2028; the exact price is (779 - 13 - 25 - 129) / 579 = 204/193; price 2
forces 1325 and lands on 23.06.2027. The code must reproduce those figures,
not the other way round. kuhy chose price 1 on 2026-09-21, accepting the
three-week miss, and moved to 2 (Mon/Fri 3, Sat/Sun 4) on 2026-10-06.
"""

from __future__ import annotations

from datetime import date
from fractions import Fraction

import pytest

from leetcode_guard._daycost import what_if
from leetcode_guard._progress import Progress
from leetcode_guard._projection import Position, project
from leetcode_guard._scenario import (
    Goal,
    Scenario,
    build_scenario,
    exact_price,
    landing_day,
)
from leetcode_guard._scenario_text import (
    BEYOND_EASY_NOTE,
    NO_PRICED_DAY,
    goal_line,
    prices_line,
    scenario_lines,
)

TODAY = date(2026, 9, 20)
TARGET = date(2027, 12, 31)
POSITION = Position(today=TODAY, charged_today=True, available=0, debt_outstanding=13)
PROGRESS = Progress(
    solved={"Easy": 58, "Medium": 0, "Hard": 0},
    total={"Easy": 966, "Medium": 2117, "Hard": 976},
    fetched_at=0.0,
)
ALL_FREE_EASY = Goal({"Easy": 837})


def never_free(_day: date) -> bool:
    return False


def worked(price: int, goal: Goal = ALL_FREE_EASY, progress: Progress = PROGRESS):
    projection = project(
        TARGET, POSITION, is_free=never_free, progress=progress, cost_of=what_if(price)
    )
    return build_scenario(
        price, goal, progress, projection, is_free=never_free
    ), projection


def test_the_original_question_at_price_one():
    scenario, _ = worked(1)

    assert scenario.needed == 779
    assert scenario.forced == 746
    assert scenario.shortfall == 33
    assert scenario.lands_on == date(2028, 1, 21)
    assert scenario.exact_price == Fraction(204, 193)
    assert scenario.minimal_price == 2
    assert scenario.minimal_lands_on == date(2027, 6, 23)


def test_the_original_question_at_price_two():
    scenario, _ = worked(2)

    assert scenario.forced == 1325
    assert scenario.shortfall == 0
    assert scenario.lands_on == date(2027, 6, 23) == scenario.minimal_lands_on


def test_the_lines_for_the_original_question():
    scenario, _ = worked(1)

    lines = scenario_lines(scenario, ALL_FREE_EASY, PROGRESS)

    assert lines == [
        "Goal: Easy 837 (779 more).",
        "At price 1: 746 forced by 31.12.2027, 33 short of the 779 the goal needs "
        "-- reached on 21.01.2028.",
        "Price that lands the goal exactly on 31.12.2027: 1.06; smallest whole "
        "price 2, which lands it on 23.06.2027.",
    ]
    assert prices_line(1) == "Prices: Tue/Wed/Thu cost 1, Mon/Fri/Sat/Sun cost 2."
    assert prices_line(2) == (
        "Prices: Tue/Wed/Thu cost 2, Mon/Fri cost 3, Sat/Sun cost 4."
    )


def test_a_price_that_makes_it_says_so_without_a_shortfall():
    scenario, _ = worked(2)

    lines = scenario_lines(scenario, ALL_FREE_EASY, PROGRESS)

    assert lines[1] == (
        "At price 2: 1325 forced by 31.12.2027, the goal needs 779 -- reached on "
        "23.06.2027."
    )


def test_a_goal_already_met_needs_nothing():
    done = Goal({"Easy": 50})
    scenario, projection = worked(2, done)

    assert scenario.needed == 0
    assert scenario.lands_on == projection.first_day
    assert scenario_lines(scenario, done, PROGRESS) == [
        "Goal: Easy 50 (0 more).",
        "The goal is already reached.",
    ]


def test_a_goal_beyond_the_site_is_named_and_not_worked():
    too_many = Goal({"Easy": 1000, "Medium": 3000})
    scenario, _ = worked(2, too_many)

    assert too_many.unreachable(PROGRESS) == ["Easy", "Medium"]
    assert scenario_lines(scenario, too_many, PROGRESS) == [
        "Goal: Easy 1000 (942 more), Medium 3000 (3000 more).",
        "Easy 1000 exceeds the 966 on the site.",
        "Medium 3000 exceeds the 2117 on the site.",
    ]


def test_goals_across_difficulties_sum_their_shortfalls_and_say_so():
    mixed = Goal({"Easy": 837, "Hard": 10})
    scenario, _ = worked(2, mixed)

    assert mixed.beyond_easy()
    assert not ALL_FREE_EASY.beyond_easy()
    assert scenario.needed == 789
    assert goal_line(mixed, PROGRESS) == "Goal: Easy 837 (779 more), Hard 10 (10 more)."
    assert scenario_lines(scenario, mixed, PROGRESS)[-1] == BEYOND_EASY_NOTE


def test_banked_credits_raise_the_price_and_debt_lowers_it():
    """215/193 is (779 - 13 debt + 33 banked - 154 fixed or flat) / 579 units.
    Banked credits are solves the profile already counts, so they lower what
    the lock forces and the price has to rise to make up for them."""
    banked = Position(
        today=TODAY, charged_today=True, available=33, debt_outstanding=13
    )
    projection = project(
        TARGET, banked, is_free=never_free, progress=PROGRESS, cost_of=what_if(1)
    )
    scenario = build_scenario(
        1, ALL_FREE_EASY, PROGRESS, projection, is_free=never_free
    )

    assert exact_price(projection, 779, is_free=never_free) == Fraction(215, 193)
    assert scenario.forced == 713
    assert scenario.lands_on is not None
    assert scenario.lands_on > TARGET


def test_a_target_with_no_priced_day_has_no_price():
    """Asking about today, already settled: nothing between now and then is
    priced in base units, so no price could land anything."""
    projection = project(TODAY, POSITION, is_free=never_free, progress=PROGRESS)
    scenario = build_scenario(
        2, ALL_FREE_EASY, PROGRESS, projection, is_free=never_free
    )

    assert scenario.exact_price is None
    assert scenario.minimal_price is None
    assert scenario.minimal_lands_on is None
    assert scenario_lines(scenario, ALL_FREE_EASY, PROGRESS)[2] == NO_PRICED_DAY


def test_a_calendar_that_is_all_free_never_lands():
    projection = project(TARGET, POSITION, is_free=lambda _d: True, progress=None)

    assert (
        landing_day(projection, 100, is_free=lambda _d: True, cost_of=what_if(2))
        is None
    )
    scenario = Scenario(TARGET, 2, 1, 0, None, Fraction(1), 1, None)
    assert (
        "never within the horizon"
        in scenario_lines(scenario, ALL_FREE_EASY, PROGRESS)[1]
    )


@pytest.mark.parametrize("price", [1, 2, 3])
def test_the_minimal_price_lands_on_or_before_the_target(price: int):
    scenario, _ = worked(price)

    assert scenario.minimal_lands_on is not None
    assert scenario.minimal_lands_on <= TARGET
