"""Per-problem submission history: every attempt on one slug, and its code.

Display-only (``test_display_only_imports`` bans every decider from it): it
feeds ``history/<slug>.json``, the context a coaching Claude reads. Nothing here
may mint, charge or unlock.

Measured 2026-11-22 with a live cookie (slug ``matrix-diagonal-sum``,
``probe/submission_shape.py``): ``questionSubmissionList`` lists every
submission on the problem, failed ones included (``Accepted``, ``Wrong Answer``,
``Compile Error``), 20 a page with ``hasNext``, each with ``id statusDisplay
lang timestamp runtime memory``; ``timestamp`` is Unix seconds as a string.
``submissionDetails(id)`` returns the ``code``. Both need the session cookie.

Two-valued like ``_attempt_queries``: ``None`` is "could not check" (transport
error, GraphQL error, or the HTTP 200 with a null payload of an expired session
or a rate limit), never "no submissions".
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from leetcode_guard._leetcode import GraphQLResult, PostFn

_logger: Final = logging.getLogger(__name__)

PAGE_SIZE: Final = 20
"""The server's page; ``fetch_page`` offsets advance by it."""

_LIST: Final = "questionSubmissionList"
_DETAIL: Final = "submissionDetails"

LIST_QUERY: Final = """
query submissionList($offset: Int!, $limit: Int!, $questionSlug: String!) {
  questionSubmissionList(offset: $offset, limit: $limit, questionSlug: $questionSlug) {
    hasNext
    submissions { id statusDisplay lang timestamp runtime memory }
  }
}
"""

DETAIL_QUERY: Final = """
query submissionDetails($submissionId: Int!) {
  submissionDetails(submissionId: $submissionId) { code }
}
"""


@dataclass(frozen=True)
class HistoryRow:
    """One submission on a problem, any status."""

    submission_id: str
    status: str
    lang: str
    at: int
    """Unix seconds."""
    runtime: str
    memory: str


@dataclass(frozen=True)
class HistoryPage:
    """One page of ``questionSubmissionList``, newest first."""

    rows: tuple[HistoryRow, ...]
    has_next: bool


def _payload(result: GraphQLResult, field: str) -> dict[str, object] | None:
    """The field's object, or ``None`` after logging why it is unreadable."""
    if result.transport_error is not None:
        reason = f"cannot reach LeetCode: {result.transport_error}"
    elif result.errors:
        reason = f"LeetCode rejected the query: {'; '.join(result.errors)}"
    else:
        found = None if result.data is None else result.data.get(field)
        if isinstance(found, dict):
            return found
        reason = "HTTP 200 with no payload (expired session or rate limit)"
    _logger.warning("%s could not be checked: %s", field, reason)
    return None


def fetch_page(post: PostFn, slug: str, offset: int) -> HistoryPage | None:
    """One page of the slug's submissions; malformed rows are dropped and logged."""
    variables: dict[str, object] = {
        "offset": offset,
        "limit": PAGE_SIZE,
        "questionSlug": slug,
    }
    found = _payload(post(LIST_QUERY, variables), _LIST)
    raw = None if found is None else found.get("submissions")
    if not isinstance(raw, list):
        if found is not None:
            _logger.warning("%s: no submissions list for %s", _LIST, slug)
        return None
    parsed = [_parse_row(item) for item in raw]
    rows = tuple(item for item in parsed if item is not None)
    if len(rows) != len(raw):
        _logger.warning("%s: dropped %d malformed row(s)", _LIST, len(raw) - len(rows))
    return HistoryPage(rows, has_next=found.get("hasNext") is True)


def fetch_code(post: PostFn, submission_id: str) -> str | None:
    """The submitted code, or ``None`` when it cannot be read."""
    found = _payload(post(DETAIL_QUERY, {"submissionId": int(submission_id)}), _DETAIL)
    code = None if found is None else found.get("code")
    return code if isinstance(code, str) else None


def _text(item: dict[str, object], key: str) -> str:
    """A string field, ``""`` when absent or of another type."""
    value = item.get(key)
    return value if isinstance(value, str) else ""


def _parse_row(item: object) -> HistoryRow | None:
    """One row, or ``None`` when its id, status or timestamp is off."""
    if not isinstance(item, dict):
        return None
    sub_id, status, stamp = (
        _text(item, key) for key in ("id", "statusDisplay", "timestamp")
    )
    if not (sub_id.isascii() and sub_id.isdigit() and status):
        return None
    if not (stamp.isascii() and stamp.isdigit()):
        return None
    return HistoryRow(
        sub_id,
        status,
        _text(item, "lang"),
        int(stamp),
        _text(item, "runtime"),
        _text(item, "memory"),
    )
