"""The profile query behind the status app's Profile tab.

Its own module because ``_queries.py`` is near the line cap. Same standing as
the documents there: run against the live endpoint, shapes copied from what
came back, because introspection is disabled on leetcode.com/graphql.
"""

from __future__ import annotations

from typing import Final

PROFILE_QUERY: Final = """
query profile($username: String!) {
  allQuestionsCount {
    difficulty
    count
  }
  matchedUser(username: $username) {
    submitStatsGlobal {
      acSubmissionNum {
        difficulty
        count
        submissions
      }
      totalSubmissionNum {
        difficulty
        count
        submissions
      }
    }
    userCalendar {
      streak
      totalActiveDays
      submissionCalendar
    }
  }
}
"""
"""Difficulty split, submission calendar and acceptance, in one public request.

A superset of :data:`~leetcode_guard._queries.PROGRESS_QUERY`, so
:func:`~leetcode_guard._progress.parse_progress` reads it unchanged and one
request refreshes both mirrors. Measured on 2026-10-23 against ``kuchy``:

* Every ``acSubmissionNum`` / ``totalSubmissionNum`` row carries ``count``
  (distinct problems) **and** ``submissions`` (attempts). The profile page's
  acceptance figure is ``ac.submissions / total.submissions`` on the ``All``
  row -- 213 / 846 that day. ``count`` gives a different, wrong number.
* ``submissionCalendar`` is a JSON object **inside a string**, keyed by
  UTC-midnight Unix seconds as strings (``"1792627200"`` = 2026-10-22). It is a
  rolling year: the first key was 2026-05-17 although ``activeYears`` also
  listed 2025.
* ``userCalendar.streak`` (19 that day) is LeetCode's max streak over that
  window; ``totalActiveDays`` was 63.
* Medium and Hard came back as a real ``0`` -- a matched user's zero is data.
* An unknown username answers HTTP 200 with the GraphQL error "That user does
  not exist." and no data at all; without the error, ``matchedUser: null``
  beside a complete ``allQuestionsCount`` (the 2026-09-19 measurement in
  ``_queries.py``). Either way the answer is "could not check", never zeros.
"""


def profile_variables(username: str) -> dict[str, object]:
    """Build variables for :data:`PROFILE_QUERY`."""
    return {"username": username}
