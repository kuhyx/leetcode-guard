"""The what-if arithmetic, pinned to the question that created it.

Asked 2026-09-20: "by how much do I raise the Tue-Thu price to have solved all
837 free Easy problems by 31.12.2027?" -- from 58 solved, 13 credits of debt,
nothing banked. Worked by hand first: 201 Tue-Thu days plus 266 doubled days
between 21.09.2026 and 31.12.2027, so price 1 forces 733 + 13 = 746 of the 779
needed and lands on 21.01.2028; the exact price is 766/733; price 2 lands on
22.05.2027. The code must reproduce those figures, not the other way round.
kuhy chose price 1 on 2026-09-21, accepting the three-week miss.
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
    assert scenario.exact_price == Fraction(766, 733)
    assert scenario.minimal_price == 2
    assert scenario.minimal_lands_on == date(2027, 5, 22)


def test_the_original_question_at_price_two():
    scenario, _ = worked(2)

    assert scenario.forced == 1479
    assert scenario.shortfall == 0
    assert scenario.lands_on == date(2027, 5, 22) == scenario.minimal_lands_on


def test_the_lines_for_the_original_question():
    scenario, _ = worked(1)

    lines = scenario_lines(scenario, ALL_FREE_EASY, PROGRESS)

    assert lines == [
        "Goal: Easy 837 (779 more).",
        "At price 1: 746 forced by 31.12.2027, 33 short of the 779 the goal needs "
        "-- reached on 21.01.2028.",
        "Price that lands the goal exactly on 31.12.2027: 1.05; smallest whole "
        "price 2, which lands it on 22.05.2027.",
    ]
    assert prices_line(1) == "Prices: Tue/Wed/Thu cost 1, Mon/Fri/Sat/Sun cost 2."


def test_a_price_that_makes_it_says_so_without_a_shortfall():
    scenario, _ = worked(2)

    lines = scenario_lines(scenario, ALL_FREE_EASY, PROGRESS)

    assert lines[1] == (
        "At price 2: 1479 forced by 31.12.2027, the goal needs 779 -- reached on "
        "22.05.2027."
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
    """766/733 is (779 - 13 debt + 0 banked) / 733 units. Banked credits are
    solves the profile already counts, so they lower what the lock forces
    and the price has to rise to make up for them."""
    banked = Position(
        today=TODAY, charged_today=True, available=33, debt_outstanding=13
    )
    projection = project(
        TARGET, banked, is_free=never_free, progress=PROGRESS, cost_of=what_if(1)
    )
    scenario = build_scenario(
        1, ALL_FREE_EASY, PROGRESS, projection, is_free=never_free
    )

    assert exact_price(projection, 779, is_free=never_free) == Fraction(799, 733)
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


def test_days_before_the_reprice_count_at_their_fixed_price():
    """An unsettled Sunday 20.09.2026 costs 2 whatever the what-if says, and
    is subtracted before the base units are solved for."""
    unsettled = Position(
        today=TODAY, charged_today=False, available=0, debt_outstanding=0
    )
    projection = project(
        date(2026, 9, 22),
        unsettled,
        is_free=never_free,
        progress=None,
        cost_of=what_if(5),
    )

    # Sun 20 = 2 fixed; Mon 21 = 2 units, Tue 22 = 1 unit.
    assert projection.base_cost == 2 + 10 + 5
    assert exact_price(projection, 2 + 9, is_free=never_free) == Fraction(9, 3)
    assert exact_price(projection, 1, is_free=never_free) == Fraction(0)
    # A free Monday leaves one unit, and the fixed Sunday still comes off.
    monday_free = {date(2026, 9, 21)}.__contains__
    assert exact_price(projection, 2 + 9, is_free=monday_free) == Fraction(9, 1)


def test_free_days_are_skipped_by_the_landing_walk():
    only_weekday_free = {date(2026, 9, 21), date(2026, 9, 22)}
    projection = project(
        date(2026, 9, 30),
        Position(today=TODAY, charged_today=True, available=0, debt_outstanding=0),
        is_free=only_weekday_free.__contains__,
        progress=None,
    )

    # Wed 23 (2) + Thu 24 (2) = 4, Fri 25 (4) reaches 8.
    assert landing_day(
        projection, 8, is_free=only_weekday_free.__contains__, cost_of=what_if(2)
    ) == date(2026, 9, 25)
    assert landing_day(
        projection, 5, is_free=only_weekday_free.__contains__, cost_of=what_if(2)
    ) == date(2026, 9, 25)
    assert landing_day(
        projection, 4, is_free=only_weekday_free.__contains__, cost_of=what_if(2)
    ) == date(2026, 9, 24)


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
