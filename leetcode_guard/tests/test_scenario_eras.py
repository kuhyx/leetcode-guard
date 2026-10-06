"""What-if arithmetic across the reprice boundary. Continued from
:mod:`test_scenario`."""

from __future__ import annotations

from datetime import date
from fractions import Fraction

from leetcode_guard._daycost import what_if
from leetcode_guard._projection import Position, project
from leetcode_guard._scenario import exact_price, landing_day
from leetcode_guard.tests.test_scenario import TODAY, never_free


def test_days_before_the_reprice_count_at_their_fixed_price():
    """An unsettled Tuesday 06.10.2026 costs 1 whatever the what-if says, and
    is subtracted before the base units are solved for. So is the flat credit
    on a Friday, which scales with nothing."""
    unsettled = Position(
        today=date(2026, 10, 6), charged_today=False, available=0, debt_outstanding=0
    )
    projection = project(
        date(2026, 10, 9),
        unsettled,
        is_free=never_free,
        progress=None,
        cost_of=what_if(5),
    )

    # Tue 6 = 1 fixed; Wed 7 = 1 unit, Thu 8 = 1 unit; Fri 9 = 1 unit + 1 flat.
    assert projection.base_cost == 1 + 5 + 5 + 6
    assert exact_price(projection, 2 + 9, is_free=never_free) == Fraction(9, 3)
    assert exact_price(projection, 1, is_free=never_free) == Fraction(0)
    # A free Wednesday leaves two units; the fixed Tuesday and Friday's flat
    # credit still come off.
    wednesday_free = {date(2026, 10, 7)}.__contains__
    assert exact_price(projection, 2 + 9, is_free=wednesday_free) == Fraction(9, 2)


def test_a_range_wholly_before_the_reprice_has_no_price():
    """Every day is fixed, so no price could land anything."""
    unsettled = Position(
        today=TODAY, charged_today=False, available=0, debt_outstanding=0
    )
    projection = project(
        date(2026, 9, 22), unsettled, is_free=never_free, progress=None
    )

    assert exact_price(projection, 5, is_free=never_free) is None


def test_free_days_are_skipped_by_the_landing_walk():
    wed_thu_free = {date(2026, 10, 7), date(2026, 10, 8)}
    projection = project(
        date(2026, 10, 14),
        Position(
            today=date(2026, 10, 6),
            charged_today=True,
            available=0,
            debt_outstanding=0,
        ),
        is_free=wed_thu_free.__contains__,
        progress=None,
    )

    # Fri 9 (3) -> 3, Sat 10 (4) -> 7, Sun 11 (4) -> 11.
    assert landing_day(
        projection, 11, is_free=wed_thu_free.__contains__, cost_of=what_if(2)
    ) == date(2026, 10, 11)
    assert landing_day(
        projection, 5, is_free=wed_thu_free.__contains__, cost_of=what_if(2)
    ) == date(2026, 10, 10)
    assert landing_day(
        projection, 3, is_free=wed_thu_free.__contains__, cost_of=what_if(2)
    ) == date(2026, 10, 9)
