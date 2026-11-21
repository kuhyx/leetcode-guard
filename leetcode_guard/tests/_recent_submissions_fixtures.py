"""``recentSubmissionList`` as LeetCode answered it on 2026-11-21.

Probed live that day, signed out (no cookie): the query answers, returns at most
20 rows, and each row has exactly the keys below. ``statusDisplay`` was seen as
``Accepted``, ``Wrong Answer``, ``Runtime Error`` and ``Compile Error``;
``timestamp`` is Unix seconds delivered as a **string**. A fixture can only
repeat what its author believed, so ``scripts/verify_recent_submissions.py``
checks this shape against the real endpoint.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard.tests._net_fixtures import submission_row

if TYPE_CHECKING:
    from collections.abc import Sequence

ROW_KEYS = frozenset({"id", "lang", "statusDisplay", "timestamp", "title", "titleSlug"})
"""The keys of one row, exactly."""
MAX_ROWS = 20
"""The server caps a page at 20 rows whatever ``limit`` asks for."""
STATUSES = ("Accepted", "Wrong Answer", "Runtime Error", "Compile Error")
"""The ``statusDisplay`` values seen; the list is open, not an enum."""


def recent_submission_row(
    submission_id: str,
    slug: str,
    *,
    status: str = "Wrong Answer",
    timestamp: int = 1_700_000_000,
    lang: str = "python3",
) -> dict[str, Any]:
    """One row shaped exactly like the live ``recentSubmissionList`` array."""
    row = submission_row(submission_id, slug, timestamp=timestamp, lang=lang)
    del row["langName"]
    return {**row, "statusDisplay": status}


def recent_submissions_result(rows: Sequence[object]) -> GraphQLResult:
    """Wrap rows in their envelope."""
    return GraphQLResult(data={"recentSubmissionList": list(rows)})
