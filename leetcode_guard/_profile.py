"""The LeetCode profile as the status app's Profile tab shows it.

Display only, like :mod:`leetcode_guard._progress`: nothing that decides,
charges or credits may read anything here (``test_push_trigger.py`` walks the
import graph to prove it).

Three-valued throughout. A profile is fully readable or ``None``; an
unreadable calendar or an attempt-free account leaves *that* figure ``None``.
Never a zero standing in for "could not check" -- an unknown handle answers
HTTP 200 with a complete denominator, so a good total says nothing about the
numerator (``_profile_query``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import json
import logging
from typing import Any, Final

from leetcode_guard._progress import parse_progress

_logger: Final = logging.getLogger(__name__)

_ALL: Final = "All"
_ONE_DAY: Final = timedelta(days=1)
_PERCENT: Final = 100.0
_RATE_DIGITS: Final = 1


@dataclass(frozen=True)
class Profile:
    """One profile fetch.

    Attributes:
        solved: Distinct problems solved per difficulty.
        total: LeetCode's own denominator per difficulty.
        calendar: Submissions per UTC day (``YYYY-MM-DD``) over LeetCode's
            rolling year, or ``None`` when it could not be read.
        acceptance_rate: Accepted / all submissions, percent, or ``None``
            when there are no submissions to divide by.
        fetched_at: Unix seconds of the fetch.
        credit_count: The gate's credit count at fetch time. A different count
            means a solve landed, which refetches regardless of age.
    """

    solved: dict[str, int]
    total: dict[str, int]
    calendar: dict[str, int] | None
    acceptance_rate: float | None
    fetched_at: float
    credit_count: int = 0


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _all_submissions(rows: object) -> int | None:
    """The ``submissions`` figure of the ``All`` row, or ``None``."""
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and row.get("difficulty") == _ALL:
            value = row.get("submissions")
            return value if _is_count(value) else None
    return None


def _acceptance(stats: dict[str, Any]) -> float | None:
    """The profile page's acceptance percentage, or ``None``."""
    accepted = _all_submissions(stats.get("acSubmissionNum"))
    attempted = _all_submissions(stats.get("totalSubmissionNum"))
    if accepted is None or not attempted:
        return None
    return round(_PERCENT * accepted / attempted, _RATE_DIGITS)


def parse_calendar(raw: object) -> dict[str, int] | None:
    """Read ``userCalendar`` into submissions per UTC day.

    All or nothing: one malformed key returns ``None`` rather than a calendar
    with a hole in it, because a hole silently breaks a streak.
    """
    if not isinstance(raw, dict):
        return None
    payload = raw.get("submissionCalendar")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError as exc:
            _logger.warning("submission calendar is not JSON: %s", exc)
            return None
    if not isinstance(payload, dict):
        return None
    days: dict[str, int] = {}
    for key, count in payload.items():
        if not str(key).isdigit() or not _is_count(count):
            _logger.warning("submission calendar holds %r: %r", key, count)
            return None
        day = datetime.fromtimestamp(int(key), tz=UTC).date().isoformat()
        days[day] = days.get(day, 0) + count
    return days


def parse_profile(
    data: object, *, fetched_at: float, credit_count: int = 0
) -> Profile | None:
    """Read a :data:`~leetcode_guard._profile_query.PROFILE_QUERY` payload."""
    progress = parse_progress(data, fetched_at=fetched_at)
    if progress is None or not isinstance(data, dict):
        return None
    user = data["matchedUser"]
    return Profile(
        solved=progress.solved,
        total=progress.total,
        calendar=parse_calendar(user.get("userCalendar")),
        # parse_progress has already proved this is an object.
        acceptance_rate=_acceptance(user["submitStatsGlobal"]),
        fetched_at=fetched_at,
        credit_count=credit_count,
    )


def streaks(calendar: dict[str, int], today: date) -> tuple[int, int]:
    """``(current, longest)`` runs of days with at least one submission.

    The current run may end yesterday: a streak is alive until the day that
    would break it is over, otherwise every morning would read 0. ``today``
    is a UTC date, because the calendar's days are.
    """
    active = sorted(date.fromisoformat(day) for day, count in calendar.items() if count)
    present = set(active)
    cursor = today if today in present else today - _ONE_DAY
    current = 0
    while cursor in present:
        current += 1
        cursor -= _ONE_DAY
    longest = run = 0
    previous: date | None = None
    for day in active:
        run = run + 1 if previous is not None and day - previous == _ONE_DAY else 1
        longest = max(longest, run)
        previous = day
    return current, longest
