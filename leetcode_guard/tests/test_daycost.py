"""Tests for day cost and the day boundary."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from leetcode_guard._daycost import (
    WEEKDAY_COST,
    WEEKEND_COST,
    day_cost,
    day_key,
    local_now,
    local_today,
    parse_day,
    weekday_name,
)


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
def test_day_cost_across_a_full_week(day: date, expected: int):
    assert day_cost(day) == expected


def test_the_weekend_boundary_follows_local_time_not_utc():
    """Late Friday evening in a UTC+2 zone is still Friday, and must still cost
    one credit. Reading the same instant as UTC would say Saturday."""
    plus_two = timezone(timedelta(hours=2))
    friday_late = datetime(2026, 7, 31, 23, 30, tzinfo=plus_two)

    assert local_today(now=friday_late) == date(2026, 7, 31)
    assert day_cost(local_today(now=friday_late)) == WEEKDAY_COST
    assert friday_late.astimezone(timezone.utc).date() == date(2026, 7, 31)


def test_early_saturday_local_is_already_the_weekend():
    plus_two = timezone(timedelta(hours=2))
    saturday_early = datetime(2026, 8, 1, 0, 30, tzinfo=plus_two)

    assert day_cost(local_today(now=saturday_early)) == WEEKEND_COST
    # The same instant is still Friday in UTC -- which is exactly the bug.
    assert saturday_early.astimezone(timezone.utc).date() == date(2026, 7, 31)


def test_injected_now_is_returned_verbatim():
    moment = datetime(2026, 7, 27, 9, 0, tzinfo=timezone.utc)

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
