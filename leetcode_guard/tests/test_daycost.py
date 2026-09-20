"""Tests for day cost and the day boundary."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from leetcode_guard._daycost import (
    CURRENT_PRICING,
    ORIGINAL_PRICING,
    REPRICE_DATE,
    Pricing,
    day_cost,
    day_key,
    local_now,
    local_today,
    parse_day,
    pricing_for,
    weekday_name,
    what_if,
)

WEEKDAY_COST = ORIGINAL_PRICING.base_cost
WEEKEND_COST = ORIGINAL_PRICING.doubled_cost
"""The pre-reprice prices; the July 2026 week below is priced under them."""


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
        (date(2026, 9, 21), 4),  # Monday -- the first repriced day
        (date(2026, 9, 22), 2),
        (date(2026, 9, 23), 2),
        (date(2026, 9, 24), 2),
        (date(2026, 9, 25), 4),  # Friday
        (date(2026, 9, 26), 4),  # Saturday
        (date(2026, 9, 27), 4),  # Sunday
    ],
)
def test_day_cost_across_the_first_repriced_week(day: date, expected: int):
    """Tue-Thu cost 2, Mon/Fri/Sat/Sun cost twice that, from 2026-09-21."""
    assert day_cost(day) == expected


def test_the_day_before_the_reprice_keeps_the_original_price():
    """Sunday 2026-09-20 was charged 2 before the rule changed; re-pricing it
    would turn a settled day into a different amount of debt."""
    assert date(2026, 9, 21) == REPRICE_DATE
    assert day_cost(REPRICE_DATE - timedelta(days=1)) == ORIGINAL_PRICING.doubled_cost
    assert pricing_for(REPRICE_DATE - timedelta(days=1)) is ORIGINAL_PRICING
    assert pricing_for(REPRICE_DATE) is CURRENT_PRICING


def test_doubled_days_cost_exactly_twice_the_base_by_construction():
    """Rule 2 is "times two, not plus one" -- a structural property, not a
    second number that could drift."""
    for base in (1, 2, 3, 7):
        pricing = CURRENT_PRICING.with_base(base)
        assert pricing.doubled_cost == 2 * base
        assert pricing.cost(date(2026, 9, 21)) == 2 * base  # Monday
        assert pricing.cost(date(2026, 9, 22)) == base  # Tuesday


def test_what_if_reprices_only_the_current_era():
    """A what-if price changes nothing that is already owed."""
    cost = what_if(7)

    assert cost(date(2026, 9, 22)) == 7
    assert cost(date(2026, 9, 21)) == 14
    assert cost(date(2026, 9, 20)) == day_cost(date(2026, 9, 20)) == 2
    assert cost(date(2026, 8, 12)) == 1


def test_describe_names_the_days_on_each_side():
    assert CURRENT_PRICING.describe() == "Tue/Wed/Thu cost 2, Mon/Fri/Sat/Sun cost 4"
    assert ORIGINAL_PRICING.describe() == "Mon/Tue/Wed/Thu/Fri cost 1, Sat/Sun cost 2"
    assert Pricing(3, frozenset()).describe() == (
        "Mon/Tue/Wed/Thu/Fri/Sat/Sun cost 3,  cost 6"
    )


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
