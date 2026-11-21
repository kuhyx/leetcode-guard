"""``recentSubmissionList``: every recent submission, not only the accepted ones.

Display-only, like ``attempts.json`` it feeds (``test_display_only_imports``
bans every decider from reaching this module). The credit path keeps reading
the accepted-only feed in ``_submissions``; nothing here may mint, charge or
unlock.

Probed live on 2026-11-21, with no cookie: the query answers signed out,
returns **at most 20 rows** whatever ``limit`` asks for, and each row has
exactly ``id lang statusDisplay timestamp title titleSlug``. ``statusDisplay``
was seen as ``Accepted``, ``Wrong Answer``, ``Runtime Error`` and ``Compile
Error``; ``timestamp`` is Unix seconds delivered as a **string**.
``scripts/verify_recent_submissions.py`` re-checks that shape against the real
endpoint, because the unit-test fixture can only repeat what its author believed.

The answer is two-valued on purpose. A list, possibly empty, is a real answer
("nothing submitted lately"). ``None`` is "could not check": a transport error,
a GraphQL error, or the HTTP 200 with a null payload LeetCode gives an expired
session or a rate limit. Collapsing the two would read silence as "no attempts".
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from leetcode_guard._leetcode import GraphQLResult, PostFn

_logger: Final = logging.getLogger(__name__)

RECENT_SUBMISSIONS_LIMIT: Final = 20
"""The server's own cap on one page."""

_FIELD: Final = "recentSubmissionList"

RECENT_SUBMISSIONS_QUERY: Final = """
query recentSubmissions($username: String!, $limit: Int!) {
  recentSubmissionList(username: $username, limit: $limit) {
    id
    lang
    statusDisplay
    timestamp
    title
    titleSlug
  }
}
"""
"""A public profile's latest submissions, every status. No auth required."""


@dataclass(frozen=True)
class RecentSubmission:
    """One submission of any status."""

    submission_id: str
    slug: str
    status: str
    """LeetCode's ``statusDisplay``, e.g. ``Wrong Answer``."""
    at: int
    """Unix seconds."""


def recent_submissions_variables(username: str) -> dict[str, object]:
    """Build variables for :data:`RECENT_SUBMISSIONS_QUERY`."""
    return {"username": username, "limit": RECENT_SUBMISSIONS_LIMIT}


def fetch_recent_submissions(
    post: PostFn, username: str
) -> list[RecentSubmission] | None:
    """Ask LeetCode for the user's latest submissions.

    Args:
        post: The network seam.
        username: The LeetCode handle. Public data.

    Returns:
        The well-formed rows (possibly none), or ``None`` for "could not
        check", with the reason logged at warning.
    """
    result = post(RECENT_SUBMISSIONS_QUERY, recent_submissions_variables(username))
    rows = _rows(result)
    if rows is None:
        return None
    parsed = [_parse_row(row) for row in rows]
    found = [item for item in parsed if item is not None]
    if len(found) != len(rows):
        _logger.warning(
            "%s: dropped %d malformed row(s) of %d",
            _FIELD,
            len(rows) - len(found),
            len(rows),
        )
    return found


def _rows(result: GraphQLResult) -> list[object] | None:
    """The raw rows, or ``None`` after logging why the answer is unreadable."""
    if result.transport_error is not None:
        reason = f"cannot reach LeetCode: {result.transport_error}"
    elif result.errors:
        reason = f"LeetCode rejected the query: {'; '.join(result.errors)}"
    elif result.data is None or result.data.get(_FIELD) is None:
        reason = "HTTP 200 with no list (expired session or rate limit)"
    elif not isinstance(result.data[_FIELD], list):
        reason = f"a {type(result.data[_FIELD]).__name__} where the list belongs"
    else:
        rows: list[object] = result.data[_FIELD]
        return rows
    _logger.warning("%s could not be checked: %s", _FIELD, reason)
    return None


def _parse_row(row: object) -> RecentSubmission | None:
    """One row, or ``None`` when any field is off."""
    if not isinstance(row, dict):
        return None
    sub_id, slug, status = row.get("id"), row.get("titleSlug"), row.get("statusDisplay")
    at = _seconds(row.get("timestamp"))
    if isinstance(sub_id, int) and not isinstance(sub_id, bool):
        sub_id = str(sub_id)
    if not (isinstance(sub_id, str) and sub_id and at is not None):
        return None
    if not (isinstance(slug, str) and slug and isinstance(status, str) and status):
        return None
    return RecentSubmission(sub_id, slug, status, at)


def _seconds(raw: object) -> int | None:
    """Unix seconds from the string LeetCode sends (an int is tolerated)."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isascii() and raw.isdigit():
        return int(raw)
    return None
