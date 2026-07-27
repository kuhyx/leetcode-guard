"""The GraphQL documents this app sends, and nothing else.

All three were run against the live endpoint on 2026-07-27 and the shapes below
are what it actually returned, not what a schema promised. Schema introspection
is **disabled** on leetcode.com/graphql (``{__schema{...}}`` returns "Query
unavailable"), so these cannot be regenerated -- they can only be copied from a
browser network tab. Treat them as verified constants.
"""

from __future__ import annotations

from typing import Final

from leetcode_guard._constants import RECENT_AC_LIMIT

POOL_QUERY: Final = """
query problemsetQuestionList($limit: Int!, $skip: Int!) {
  problemsetQuestionList: questionList(
    categorySlug: ""
    limit: $limit
    skip: $skip
    filters: {}
  ) {
    total: totalNum
    questions: data {
      frontendQuestionId: questionFrontendId
      title
      titleSlug
      difficulty
      acRate
      paidOnly: isPaidOnly
      status
      topicTags {
        name
        slug
      }
    }
  }
}
"""
"""Every problem, paged. No auth required.

Deliberately carries no ``filters`` argument beyond the empty literal:

* There is **no server-side sort**. ``sortBy`` fails with ``Unknown argument
  "sortBy" on field "questionList"``, so ordering by difficulty then acceptance
  happens locally regardless -- and once the whole set is local, filtering
  server-side saves nothing.
* A difficulty filter, if ever wanted, must be passed as a **typed variable**::

      query q($f: QuestionListFilterInput!) { questionList(..., filters: $f) }

  with ``{"f": {"difficulty": "EASY"}}``. Inlining it as a string literal fails
  with ``Expected type "DifficultyEnum", found "EASY"``.

Field notes:

* ``acRate`` here is a **percent** (57.879...). The custom-list query
  (``favoriteQuestionList``) returns the same quantity as a *fraction* and
  difficulty in UPPERCASE -- the two are not interchangeable.
* ``status`` is per-session, not per-user: ``null`` anonymously, ``"ac"`` /
  ``"notac"`` with cookies. One authenticated pass therefore yields metadata
  and solved-state together.
"""

RECENT_AC_QUERY: Final = """
query recentAcSubmissions($username: String!, $limit: Int!) {
  recentAcSubmissionList(username: $username, limit: $limit) {
    id
    title
    titleSlug
    timestamp
    lang
    langName
    statusDisplay
  }
}
"""
"""Recently accepted submissions for any public profile. No auth required.

This is the whole unlock condition. Two properties matter:

* The server **caps the result at 20 rows** regardless of ``limit`` (verified by
  asking for 100 and receiving 20).
* ``timestamp`` is Unix seconds delivered as a **string**.

A nonexistent username returns a GraphQL error ("That user does not exist."),
which is how a misconfiguration is told apart from an outage.
"""

STATEMENT_QUERY: Final = """
query questionContent($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    titleSlug
    title
    difficulty
    content
  }
}
"""
"""One problem's statement, for the offline mirror. No auth required for free
problems; premium ones return ``content: null``, which is why they are excluded
from the suggestion list in the first place."""


IDENTITY_QUERY: Final = """
query identityProbe {
  allQuestionsCount {
    difficulty
    count
  }
}
"""
"""The cheapest public query that proves we are talking to LeetCode.

Used by :func:`leetcode_guard._leetcode.looks_like_leetcode` rather than a GET
of the homepage. Measured: ``https://leetcode.com/`` returns **HTTP 403** to a
plain request -- Cloudflare bot protection -- while this POST returns 200. An
earlier draft fetched the homepage and therefore reported "not LeetCode" on a
perfectly healthy connection, which would have classified a genuine LeetCode
outage as local tampering and demanded a written explanation for it.

Probing the GraphQL endpoint is also simply more honest: it is the dependency
the gate actually has, not a proxy for it.
"""


def pool_variables(*, skip: int, limit: int) -> dict[str, int]:
    """Build variables for :data:`POOL_QUERY`."""
    return {"limit": limit, "skip": skip}


def recent_ac_variables(username: str) -> dict[str, object]:
    """Build variables for :data:`RECENT_AC_QUERY`."""
    return {"username": username, "limit": RECENT_AC_LIMIT}


def statement_variables(title_slug: str) -> dict[str, object]:
    """Build variables for :data:`STATEMENT_QUERY`."""
    return {"titleSlug": title_slug}
