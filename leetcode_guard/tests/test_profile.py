"""Tests for the profile parse: difficulty split, calendar, streaks, acceptance.

The rule under test everywhere: a profile is either fully readable or
``None``. Never zeros for "could not check" -- an unknown handle answers HTTP
200 with a healthy denominator and ``matchedUser: null`` (2026-10-23).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from leetcode_guard._profile import parse_calendar, parse_profile, streaks
from leetcode_guard._profile_query import PROFILE_QUERY, profile_variables
from leetcode_guard.tests._profile_fixtures import (
    calendar_text,
    day_seconds,
    profile_data,
    unknown_user_data,
)

TODAY = date(2026, 10, 23)


def test_a_healthy_payload_reads_every_field():
    calendar = calendar_text({TODAY: 2, TODAY - timedelta(days=1): 31})

    profile = parse_profile(
        profile_data(calendar=calendar), fetched_at=5.0, credit_count=7
    )

    assert profile is not None
    assert profile.solved == {"Easy": 142, "Medium": 0, "Hard": 0}
    assert profile.total == {"Easy": 972, "Medium": 2131, "Hard": 984}
    assert profile.calendar == {"2026-10-23": 2, "2026-10-22": 31}
    assert profile.acceptance_rate == pytest.approx(25.2)
    assert profile.fetched_at == 5.0
    assert profile.credit_count == 7


def test_an_unknown_user_is_none_not_zeros():
    assert parse_profile(unknown_user_data(), fetched_at=0.0) is None


@pytest.mark.parametrize("data", [None, [], {"allQuestionsCount": []}])
def test_an_unreadable_payload_is_none(data: object):
    assert parse_profile(data, fetched_at=0.0) is None


def test_no_submissions_is_an_unknown_rate_not_zero():
    profile = parse_profile(
        profile_data(ac_submissions=0, all_submissions=0), fetched_at=0.0
    )

    assert profile is not None
    assert profile.acceptance_rate is None


def test_missing_submission_rows_leave_the_rate_unknown():
    data = profile_data()
    del data["matchedUser"]["submitStatsGlobal"]["totalSubmissionNum"]

    profile = parse_profile(data, fetched_at=0.0)

    assert profile is not None
    assert profile.acceptance_rate is None


def test_a_malformed_all_row_leaves_the_rate_unknown():
    data = profile_data()
    stats = data["matchedUser"]["submitStatsGlobal"]
    stats["acSubmissionNum"][0]["submissions"] = "213"
    stats["totalSubmissionNum"].insert(0, "junk")

    profile = parse_profile(data, fetched_at=0.0)

    assert profile is not None
    assert profile.acceptance_rate is None


def test_no_all_row_leaves_the_rate_unknown():
    data = profile_data()
    stats = data["matchedUser"]["submitStatsGlobal"]
    stats["acSubmissionNum"] = stats["acSubmissionNum"][1:]

    profile = parse_profile(data, fetched_at=0.0)

    assert profile is not None
    assert profile.acceptance_rate is None


def test_an_unreadable_calendar_keeps_the_rest():
    profile = parse_profile(profile_data(calendar="{not json"), fetched_at=0.0)

    assert profile is not None
    assert profile.calendar is None
    assert profile.solved["Easy"] == 142


def test_the_calendar_merges_same_utc_day_keys():
    key = day_seconds(TODAY)
    later = str(int(key) + 3600)

    assert parse_calendar({"submissionCalendar": {key: 1, later: 2}}) == {
        "2026-10-23": 3
    }


@pytest.mark.parametrize(
    "raw",
    [
        None,
        {},
        {"submissionCalendar": 5},
        {"submissionCalendar": "[1, 2]"},
        {"submissionCalendar": {"abc": 1}},
        {"submissionCalendar": {"1792627200": -1}},
        {"submissionCalendar": {"1792627200": True}},
    ],
)
def test_a_malformed_calendar_is_none(raw: object):
    assert parse_calendar(raw) is None


def test_current_streak_counts_back_from_today():
    active = {TODAY - timedelta(days=offset): 1 for offset in range(3)}

    assert streaks(_iso(active), TODAY) == (3, 3)


def test_a_streak_ending_yesterday_is_still_current():
    """Otherwise every morning shows 0 until the first submission."""
    active = {TODAY - timedelta(days=offset): 1 for offset in (1, 2)}

    assert streaks(_iso(active), TODAY) == (2, 2)


def test_a_gap_before_yesterday_ends_the_current_streak():
    active = {TODAY - timedelta(days=offset): 1 for offset in (2, 3, 4, 5, 9)}

    assert streaks(_iso(active), TODAY) == (0, 4)


def test_zero_count_days_do_not_count():
    assert streaks({TODAY.isoformat(): 0}, TODAY) == (0, 0)


def test_the_query_asks_for_everything_parsed():
    for field in ("submissionCalendar", "totalSubmissionNum", "matchedUser"):
        assert field in PROFILE_QUERY
    assert profile_variables("k") == {"username": "k"}


def _iso(days: dict[date, int]) -> dict[str, int]:
    return {day.isoformat(): count for day, count in days.items()}
