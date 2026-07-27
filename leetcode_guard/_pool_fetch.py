"""Page the whole problem set out of LeetCode.

A partial pool is still a useful pool: the suggestion list only ever shows ten
problems, so failing on page 7 of 9 is not a reason to show nothing. Every
shortfall is reported in :attr:`PoolFetch.reason` and surfaced to the user
rather than swallowed.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard._constants import POOL_MAX_PAGES, POOL_PAGE_SIZE
from leetcode_guard._problem import Problem, page_row_count, page_total, parse_questions
from leetcode_guard._queries import POOL_QUERY, pool_variables

if TYPE_CHECKING:
    from leetcode_guard._leetcode import PostFn

_logger: Final = logging.getLogger(__name__)

_POOL_FIELD: Final = "problemsetQuestionList"


@dataclass(frozen=True)
class PoolFetch:
    """The outcome of a pool refresh.

    Attributes:
        problems: Everything successfully parsed, unfiltered and unordered.
        total: The count LeetCode advertised, if it ever told us.
        complete: Whether every advertised problem was retrieved.
        reason: A sentence, always -- success included, so a log line or a
            status view never has to say "no reason given".
    """

    problems: tuple[Problem, ...]
    total: int | None
    complete: bool
    reason: str


def fetch_pool(
    post: PostFn,
    *,
    page_size: int = POOL_PAGE_SIZE,
    max_pages: int = POOL_MAX_PAGES,
) -> PoolFetch:
    """Retrieve every problem, one page at a time.

    Args:
        post: The network seam.
        page_size: Rows per request. ``questionList`` honours large values;
            only the submissions query is server-capped.
        max_pages: Runaway guard. Hitting it means the pager is looping, so it
            is reported as an incomplete fetch rather than passed off as done.

    Returns:
        Whatever was retrieved, with an explicit completeness verdict.
    """
    collected: list[Problem] = []
    total: int | None = None
    skip = 0
    for _ in range(max_pages):
        result = post(POOL_QUERY, pool_variables(skip=skip, limit=page_size))
        if result.transport_error is not None:
            return _partial(
                collected, total, f"pool fetch stopped: {result.transport_error}"
            )
        if result.errors:
            joined = "; ".join(result.errors)
            return _partial(collected, total, f"pool fetch rejected: {joined}")
        if result.data is None:
            return _partial(
                collected,
                total,
                "pool fetch got HTTP 200 with no data (expired session or rate limit)",
            )

        page = result.data.get(_POOL_FIELD)
        advertised = page_total(page)
        if advertised is not None:
            total = advertised
        returned = page_row_count(page)
        if returned == 0:
            return _finish(collected, total, "reached the end of the problem set")
        collected.extend(parse_questions(page))
        # Advance by what the server actually sent, never by what we asked for.
        # It caps a page at 100 rows without saying so, and trusting the
        # request size here silently skipped three quarters of the problem set.
        skip += returned
        if total is not None and skip >= total:
            return _finish(collected, total, f"fetched all {len(collected)} problems")

    _logger.warning(
        "pool fetch hit the %d-page guard with %d problems", max_pages, len(collected)
    )
    return _partial(collected, total, f"pool fetch hit the {max_pages}-page guard")


def _finish(problems: list[Problem], total: int | None, reason: str) -> PoolFetch:
    """Build a complete result."""
    return PoolFetch(
        problems=tuple(problems), total=total, complete=True, reason=reason
    )


def _partial(problems: list[Problem], total: int | None, reason: str) -> PoolFetch:
    """Build an incomplete result, logging why."""
    _logger.warning("%s (kept %d problems)", reason, len(problems))
    return PoolFetch(
        problems=tuple(problems), total=total, complete=False, reason=reason
    )
