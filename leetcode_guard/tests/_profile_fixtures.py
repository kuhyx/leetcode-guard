"""Payloads shaped like the live profile query, as measured on 2026-10-23.

``kuchy`` answered with every difficulty row carrying ``count`` *and*
``submissions``, a ``submissionCalendar`` that is a JSON **string** keyed by
UTC-midnight Unix seconds, and Medium/Hard at a real 0. An unknown username
answered HTTP 200 with ``matchedUser: null`` plus the GraphQL error "That user
does not exist." -- see :mod:`leetcode_guard._profile_query`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
import json
from typing import Any

from leetcode_guard._leetcode import GraphQLResult


def day_seconds(day: date) -> str:
    """The calendar's key for ``day``: UTC midnight, as a string."""
    return str(int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp()))


def calendar_text(days: dict[date, int]) -> str:
    """A ``submissionCalendar`` as LeetCode sends it: JSON inside a string."""
    return json.dumps({day_seconds(day): count for day, count in days.items()})


def _rows(counts: dict[str, int], submissions: dict[str, int]) -> list[dict[str, Any]]:
    return [
        {"difficulty": name, "count": counts[name], "submissions": submissions[name]}
        for name in ("All", "Easy", "Medium", "Hard")
    ]


def profile_data(
    *,
    solved: tuple[int, int, int] = (142, 0, 0),
    total: tuple[int, int, int] = (972, 2131, 984),
    ac_submissions: int = 213,
    all_submissions: int = 846,
    calendar: object = None,
) -> dict[str, Any]:
    """The ``data`` object of a healthy profile response."""
    easy, medium, hard = solved
    counts = {"All": easy + medium + hard, "Easy": easy, "Medium": medium, "Hard": hard}
    subs = {"All": ac_submissions, "Easy": ac_submissions, "Medium": 0, "Hard": 0}
    tried = {"All": all_submissions, "Easy": all_submissions, "Medium": 0, "Hard": 0}
    t_easy, t_medium, t_hard = total
    return {
        "allQuestionsCount": [
            {"difficulty": "All", "count": t_easy + t_medium + t_hard},
            {"difficulty": "Easy", "count": t_easy},
            {"difficulty": "Medium", "count": t_medium},
            {"difficulty": "Hard", "count": t_hard},
        ],
        "matchedUser": {
            "submitStatsGlobal": {
                "acSubmissionNum": _rows(counts, subs),
                "totalSubmissionNum": _rows(counts, tried),
            },
            "userCalendar": {
                "streak": 19,
                "totalActiveDays": 63,
                "submissionCalendar": calendar_text({})
                if calendar is None
                else calendar,
            },
        },
    }


def profile_result(**kwargs: Any) -> GraphQLResult:
    """A healthy profile response."""
    return GraphQLResult(data=profile_data(**kwargs))


def unknown_user_data() -> dict[str, Any]:
    """What an unknown handle's *data* looks like: a full denominator, no user."""
    data = profile_data()
    data["matchedUser"] = None
    return data
