"""Tests for day cost and the day boundary."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from leetcode_guard._daycost import (
    CURRENT_BASE,
    CURRENT_PRICING,
    INTERIM_DATE,
    INTERIM_PRICING,
    ORIGINAL_PRICING,
    REPRICE_DATE,
    Pricing,
    base_terms,
    day_cost,
    day_key,
    local_now,
    local_today,
    parse_day,
    pricing_for,
    surcharge_applies,
    tiered,
    weekday_name,
    what_if,
)

WEEKDAY_COST = 1
WEEKEND_COST = 2
"""The original prices; the July 2026 week below is priced under them."""


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 7, 27), WEEKDAY_COST),  # Monday
        (date(2026, 7, 28), WEEKDAY_COST),
        (date(2026, 7, 29), WEEKDAY_COST),
        (date(2026, 7, 30), WEEKDAY_COST),
        (date(2026, 7, 31), WEEKDAY_COST),  # Friday
        (date(2026, 8, 1), WEEKEND_COST),  # Saturday
        (date(2026, 8, 2), WEEKEND_COST),  # Sunday
    ],
)
def test_day_cost_across_a_full_week_before_the_reprice(day: date, expected: int):
    assert day_cost(day) == expected


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 9, 21), 2),  # Monday -- the first repriced day
        (date(2026, 9, 22), 1),
        (date(2026, 9, 23), 1),
        (date(2026, 9, 24), 1),
        (date(2026, 9, 25), 2),  # Friday
        (date(2026, 9, 26), 2),  # Saturday
        (date(2026, 9, 27), 2),  # Sunday
    ],
)
def test_day_cost_across_the_first_repriced_week(day: date, expected: int):
    """Tue-Thu cost 1, Mon/Fri/Sat/Sun cost twice that, from 2026-09-21."""
    assert day_cost(day) == expected


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 10, 7), 2),  # Wednesday -- the first day of the third era
        (date(2026, 10, 8), 2),  # Thursday
        (date(2026, 10, 9), 3),  # Friday
        (date(2026, 10, 10), 4),  # Saturday
        (date(2026, 10, 11), 4),  # Sunday
        (date(2026, 10, 12), 3),  # Monday
        (date(2026, 10, 13), 2),  # Tuesday
    ],
)
def test_day_cost_across_the_first_week_of_the_current_prices(day: date, expected: int):
    """Tue-Thu 2, Mon/Fri 3, Sat/Sun 4, from 2026-10-07."""
    assert day_cost(day) == expected


def test_each_day_keeps_the_price_of_the_era_it_fell_in():
    """Re-pricing a settled day would turn it into a different amount of debt."""
    assert date(2026, 9, 21) == INTERIM_DATE
    assert date(2026, 10, 7) == REPRICE_DATE
    assert day_cost(INTERIM_DATE - timedelta(days=1)) == 2  # Sunday, original
    assert day_cost(REPRICE_DATE - timedelta(days=1)) == 1  # Tuesday, interim
    assert pricing_for(INTERIM_DATE - timedelta(days=1)) is ORIGINAL_PRICING
    assert pricing_for(INTERIM_DATE) is INTERIM_PRICING
    assert pricing_for(REPRICE_DATE - timedelta(days=1)) is INTERIM_PRICING
    assert pricing_for(REPRICE_DATE) is CURRENT_PRICING


def test_the_current_prices_are_the_tiers_around_the_current_base():
    assert CURRENT_BASE == 2
    assert tiered(CURRENT_BASE) == CURRENT_PRICING


def test_tiers_are_base_then_one_more_then_twice_the_base():
    for base in (1, 2, 3, 7):
        pricing = tiered(base)
        assert pricing.cost(date(2026, 10, 13)) == base  # Tuesday
        assert pricing.cost(date(2026, 10, 12)) == base + 1  # Monday
        assert pricing.cost(date(2026, 10, 9)) == base + 1  # Friday
        assert pricing.cost(date(2026, 10, 10)) == 2 * base  # Saturday


def test_base_terms_reproduce_the_tiers():
    """cost == per_base * price + flat, so the what-if can solve for price."""
    for offset in range(7):
        day = date(2026, 10, 12) + timedelta(days=offset)
        per_base, flat = base_terms(day)
        for base in (1, 2, 5):
            assert per_base * base + flat == tiered(base).cost(day)


def test_what_if_reprices_only_the_current_era():
    """A what-if price changes nothing that is already owed."""
    cost = what_if(7)

    assert cost(date(2026, 10, 13)) == 7
    assert cost(date(2026, 10, 12)) == 8
    assert cost(date(2026, 10, 10)) == 14
    assert cost(date(2026, 10, 6)) == day_cost(date(2026, 10, 6)) == 1
    assert cost(date(2026, 9, 20)) == day_cost(date(2026, 9, 20)) == 2
    assert cost(date(2026, 8, 12)) == 1
    assert day_cost(date(2026, 10, 13)) == 2


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 10, 12), True),  # Monday
        (date(2026, 10, 13), False),  # Tuesday
        (date(2026, 10, 14), False),  # Wednesday
        (date(2026, 10, 15), False),  # Thursday
        (date(2026, 10, 16), True),  # Friday
        (date(2026, 10, 17), True),  # Saturday
        (date(2026, 10, 18), True),  # Sunday
    ],
)
def test_the_debt_surcharge_never_applies_on_tuesday_to_thursday(
    day: date, expected: bool
):
    assert surcharge_applies(day) is expected


def test_losing_the_tue_thu_discount_prices_a_day_like_a_friday_never_below_its_own():
    pricing = CURRENT_PRICING

    assert pricing.penalised_cost(date(2026, 10, 14)) == 3  # Wednesday -> Friday's
    assert pricing.penalised_cost(date(2026, 10, 16)) == 3  # Friday unchanged
    assert pricing.penalised_cost(date(2026, 10, 17)) == 4  # Saturday keeps its own


def test_describe_names_the_days_on_each_side():
    assert CURRENT_PRICING.describe() == (
        "Tue/Wed/Thu cost 2, Mon/Fri cost 3, Sat/Sun cost 4"
    )
    assert INTERIM_PRICING.describe() == "Tue/Wed/Thu cost 1, Mon/Fri/Sat/Sun cost 2"
    assert ORIGINAL_PRICING.describe() == "Mon/Tue/Wed/Thu/Fri cost 1, Sat/Sun cost 2"
    assert Pricing((3,) * 7, 3).describe() == "Mon/Tue/Wed/Thu/Fri/Sat/Sun cost 3"


def test_the_weekend_boundary_follows_local_time_not_utc():
    """Late Friday evening in a UTC+2 zone is still Friday, and must still cost
    one credit. Reading the same instant as UTC would say Saturday."""
    plus_two = timezone(timedelta(hours=2))
    friday_late = datetime(2026, 7, 31, 23, 30, tzinfo=plus_two)

    assert local_today(now=friday_late) == date(2026, 7, 31)
    assert day_cost(local_today(now=friday_late)) == WEEKDAY_COST
    assert friday_late.astimezone(UTC).date() == date(2026, 7, 31)


def test_early_saturday_local_is_already_the_weekend():
    plus_two = timezone(timedelta(hours=2))
    saturday_early = datetime(2026, 8, 1, 0, 30, tzinfo=plus_two)

    assert day_cost(local_today(now=saturday_early)) == WEEKEND_COST
    # The same instant is still Friday in UTC -- which is exactly the bug.
    assert saturday_early.astimezone(UTC).date() == date(2026, 7, 31)


def test_injected_now_is_returned_verbatim():
    moment = datetime(2026, 7, 27, 9, 0, tzinfo=UTC)

    assert local_now(now=moment) is moment


def test_default_now_is_timezone_aware():
    assert local_now().tzinfo is not None


def test_default_today_is_a_date():
    assert isinstance(local_today(), date)


def test_day_key_round_trips():
    day = date(2026, 7, 27)

    assert day_key(day) == "2026-07-27"
    assert parse_day(day_key(day)) == day


@pytest.mark.parametrize("text", ["", "not-a-date", "2026-13-01", "27/07/2026"])
def test_unparsable_days_return_none_rather_than_raising(text: str):
    """Aborting the load on one bad row would read as a zero balance, which is
    an accidental permanent lock."""
    assert parse_day(text) is None


def test_weekday_name():
    assert weekday_name(date(2026, 7, 27)) == "Monday"
    assert weekday_name(date(2026, 8, 1)) == "Saturday"
