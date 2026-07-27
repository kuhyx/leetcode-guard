"""Solve detection, and the three-valued answer it has to give.

The whole app hangs on one distinction. LeetCode answers an expired session, a
rate-limit and several other failures with **HTTP 200 and a null payload** --
not an error. Collapsing that into "no accepted submissions" would mean a lock
whose unlock condition can never be satisfied and which does not know it.

So a probe returns OK (we know the truth, whatever it is) or UNVERIFIABLE (we
do not). An *empty list* is a real answer and stays OK. Only absence of data is
UNVERIFIABLE.

This query needs no authentication, which is the other half of the design: the
suggestion list may quietly degrade when cookies expire, but the unlock path
never depends on them.
"""

from __future__ import annotations

from dataclasses import dataclass
import enum
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard._queries import RECENT_AC_QUERY, recent_ac_variables

if TYPE_CHECKING:
    from leetcode_guard._leetcode import PostFn

_logger: Final = logging.getLogger(__name__)

_FIELD: Final = "recentAcSubmissionList"
_NO_SUCH_USER: Final = "does not exist"


class ProbeStatus(enum.Enum):
    """Whether the answer can be believed."""

    OK = "ok"
    """We know what LeetCode thinks, including "nothing accepted recently"."""

    UNVERIFIABLE = "unverifiable"
    """We do not know. **Never** treat this as "not solved"."""


@dataclass(frozen=True)
class AcSubmission:
    """One accepted submission."""

    submission_id: str
    """LeetCode's own id. The ledger keys credits on this, which is what makes
    re-polling idempotent and lets a solve from before the lock engaged count
    without any timestamp bookkeeping."""

    title: str
    title_slug: str
    timestamp: int
    """Unix seconds. The API delivers this as a string."""
    lang: str


@dataclass(frozen=True)
class SolveProbe:
    """The result of asking "what has this user solved lately?"."""

    status: ProbeStatus
    submissions: tuple[AcSubmission, ...]
    reason: str
    """A sentence, always -- shown on the lock surface when things go wrong."""

    @property
    def usable(self) -> bool:
        """Whether :attr:`submissions` reflects reality."""
        return self.status is ProbeStatus.OK


def _unverifiable(reason: str) -> SolveProbe:
    """Build the "we could not check" answer."""
    return SolveProbe(status=ProbeStatus.UNVERIFIABLE, submissions=(), reason=reason)


def fetch_recent_ac(post: PostFn, username: str) -> SolveProbe:
    """Ask LeetCode for the user's recent accepted submissions.

    Args:
        post: The network seam.
        username: The LeetCode handle to query. Public data; no auth.

    Returns:
        An OK probe carrying up to 20 submissions (LeetCode's hard cap), or an
        UNVERIFIABLE one explaining what went wrong.
    """
    result = post(RECENT_AC_QUERY, recent_ac_variables(username))

    if result.transport_error is not None:
        return _unverifiable(f"cannot reach LeetCode: {result.transport_error}")

    if result.errors:
        joined = "; ".join(result.errors)
        if any(_NO_SUCH_USER in message for message in result.errors):
            # A configuration bug, not an outage: it will never fix itself, so
            # it is louder than the surrounding WARNINGs.
            _logger.error(
                "LeetCode username %r does not exist -- fix the configured "
                "username or the gate can never unlock",
                username,
            )
            return _unverifiable(
                f"LeetCode says the username {username!r} does not exist -- "
                "fix the configured username."
            )
        return _unverifiable(f"LeetCode rejected the query: {joined}")

    if result.data is None:
        return _unverifiable(
            "LeetCode returned HTTP 200 with no data (expired session or rate limit)"
        )

    rows = result.data.get(_FIELD)
    if rows is None:
        return _unverifiable(
            "LeetCode returned no submission list (expired session or rate limit)"
        )
    if not isinstance(rows, list):
        return _unverifiable(
            f"LeetCode returned a {type(rows).__name__} "
            "where the submission list belongs"
        )

    parsed = [_parse_submission(row) for row in rows]
    submissions = tuple(item for item in parsed if item is not None)
    if not submissions:
        return SolveProbe(
            status=ProbeStatus.OK,
            submissions=(),
            reason="no accepted submissions in the recent window",
        )
    plural = "" if len(submissions) == 1 else "s"
    return SolveProbe(
        status=ProbeStatus.OK,
        submissions=submissions,
        reason=f"{len(submissions)} recent accepted submission{plural}",
    )


def _parse_submission(row: object) -> AcSubmission | None:
    """Convert one row, or ``None`` if it is unusable.

    A malformed row is skipped with a WARNING and does **not** downgrade the
    probe: we still know what LeetCode said about every other row.
    """
    if not isinstance(row, dict):
        _logger.warning("skipping non-object submission row: %r", row)
        return None
    submission_id = row.get("id")
    slug = row.get("titleSlug")
    if submission_id is None or not isinstance(slug, str) or not slug:
        _logger.warning("skipping submission row with no id/titleSlug: %r", row)
        return None
    timestamp = _parse_timestamp(row.get("timestamp"), slug)
    if timestamp is None:
        return None
    return AcSubmission(
        submission_id=str(submission_id),
        title=str(row.get("title", slug)),
        title_slug=slug,
        timestamp=timestamp,
        lang=str(row.get("lang", "")),
    )


def _parse_timestamp(raw: object, slug: str) -> int | None:
    """Coerce the string-encoded Unix timestamp LeetCode sends."""
    if isinstance(raw, bool):
        _logger.warning("skipping submission for %s: timestamp is a bool", slug)
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        try:
            return int(raw)
        except ValueError:
            _logger.warning(
                "skipping submission for %s: timestamp %r is not an int", slug, raw
            )
            return None
    _logger.warning("skipping submission for %s: timestamp is %r", slug, raw)
    return None
