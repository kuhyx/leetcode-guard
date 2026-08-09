"""Problem metadata and the ordering the gate suggests.

Pure functions over plain data -- no network, no clock, no filesystem. The
ranking rule is the user's, verbatim: non-premium only, easiest first, and
within a difficulty the highest acceptance rate first.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard._constants import PROBLEM_URL_TEMPLATE

if TYPE_CHECKING:
    from collections.abc import Iterable

_logger: Final = logging.getLogger(__name__)

_DIFFICULTY_ORDER: Final[dict[str, int]] = {"Easy": 0, "Medium": 1, "Hard": 2}
_UNKNOWN_DIFFICULTY_RANK: Final = 3
"""Sorts after Hard. An unrecognised difficulty is a schema change, not a
reason to crash or to silently promote the problem to the top of the list."""

SOLVED_STATUS: Final = "ac"
"""What ``status`` reads when the session has solved a problem. Note the
lowercase: the *filter* vocabulary for the same concept is uppercase ``"AC"``,
and the custom-list query uses ``"TO_DO"`` -- three spellings, one idea."""


@dataclass(frozen=True)
class Problem:
    """One LeetCode problem as the pool query returns it."""

    frontend_id: str
    title: str
    title_slug: str
    difficulty: str
    """``"Easy"`` / ``"Medium"`` / ``"Hard"``, title case as returned."""
    ac_rate: float
    """Acceptance rate as a **percent**, 0-100."""
    paid_only: bool
    status: str | None
    """``None`` anonymously; ``"ac"`` / ``"notac"`` with cookies."""
    topics: tuple[str, ...] = ()

    @property
    def url(self) -> str:
        """The problem's page."""
        return PROBLEM_URL_TEMPLATE.format(slug=self.title_slug)

    @property
    def solved(self) -> bool:
        """Whether the authenticated session has solved this.

        Always ``False`` anonymously -- which is why the suggestion list says
        so out loud rather than pretending the filter ran.
        """
        return self.status == SOLVED_STATUS


def sort_key(problem: Problem) -> tuple[int, float]:
    """Rank: easiest first, then highest acceptance first."""
    return (
        _DIFFICULTY_ORDER.get(problem.difficulty, _UNKNOWN_DIFFICULTY_RANK),
        -problem.ac_rate,
    )


_TITLE_MAX_CHARS: Final = 120
"""Longest title in the live 4013-problem pool is 79 characters."""


def _one_line(title: str) -> str:
    """Flatten a title to a single bounded line.

    The lock renders titles in a non-wrapping label, so whatever the API sends
    is laid out verbatim. Two shapes of malformed title are load-bearing there,
    and both arrive in perfectly well-formed JSON:

    * an embedded newline becomes an extra rendered *row*, and eight of them
      push the surface past its 768px budget -- where a ``place``-centred frame
      clips at both edges and takes the headline and escape button with it;
    * a multi-thousand-character title asks X for a pixmap it cannot allocate,
      and Xlib's default error handler exits the process in C, killing a lock
      that is holding the global grab.

    Neither is reachable from LeetCode as it behaves today. Both are one bad
    deploy away, and the cost of collapsing whitespace here is nothing.
    """
    flattened = " ".join(title.split())
    if len(flattened) > _TITLE_MAX_CHARS:
        return flattened[: _TITLE_MAX_CHARS - 1] + "\u2026"
    return flattened


def parse_problem(row: object) -> Problem | None:
    """Convert one ``questions`` row, or ``None`` if it is unusable.

    Tolerant by design: a schema change in one field must cost that one
    problem, not the whole suggestion list.
    """
    if not isinstance(row, dict):
        _logger.warning("skipping non-object problem row: %r", row)
        return None
    slug = row.get("titleSlug")
    if not isinstance(slug, str) or not slug:
        _logger.warning("skipping problem row with no titleSlug: %r", row)
        return None
    ac_rate = row.get("acRate")
    if not isinstance(ac_rate, (int, float)) or isinstance(ac_rate, bool):
        _logger.warning("skipping problem %s: acRate is %r", slug, ac_rate)
        return None
    difficulty = row.get("difficulty")
    if not isinstance(difficulty, str):
        _logger.warning("skipping problem %s: difficulty is %r", slug, difficulty)
        return None
    return Problem(
        frontend_id=str(row.get("frontendQuestionId", "")),
        title=_one_line(str(row.get("title", slug))),
        title_slug=slug,
        difficulty=difficulty,
        ac_rate=float(ac_rate),
        paid_only=bool(row.get("paidOnly", False)),
        status=row.get("status") if isinstance(row.get("status"), str) else None,
        topics=_parse_topics(row.get("topicTags")),
    )


def _parse_topics(raw: object) -> tuple[str, ...]:
    """Pull topic slugs out of ``topicTags``, tolerating anything unexpected."""
    if not isinstance(raw, list):
        return ()
    slugs = [
        tag["slug"]
        for tag in raw
        if isinstance(tag, dict) and isinstance(tag.get("slug"), str)
    ]
    return tuple(slugs)


def parse_questions(page: object) -> list[Problem]:
    """Convert one ``problemsetQuestionList`` page into problems."""
    if not isinstance(page, dict):
        _logger.warning("pool page is not an object: %r", type(page).__name__)
        return []
    rows = page.get("questions")
    if not isinstance(rows, list):
        _logger.warning("pool page has no questions array")
        return []
    parsed = [parse_problem(row) for row in rows]
    return [problem for problem in parsed if problem is not None]


def page_row_count(page: object) -> int:
    """How many rows the server actually put in this page.

    Distinct from ``len(parse_questions(page))`` on purpose: the pager must
    advance by rows *returned*, not rows successfully parsed, or one malformed
    row would shift every subsequent page and silently drop problems.
    """
    if not isinstance(page, dict):
        return 0
    rows = page.get("questions")
    if not isinstance(rows, list):
        return 0
    return len(rows)


def page_total(page: object) -> int | None:
    """The advertised total problem count, if the page carried one."""
    if not isinstance(page, dict):
        return None
    total = page.get("total")
    if isinstance(total, bool) or not isinstance(total, int):
        return None
    return total


def rank_pool(problems: Iterable[Problem], *, exclude_solved: bool) -> list[Problem]:
    """Filter and order the suggestion list.

    Premium problems are always dropped -- they cannot be opened without a
    subscription, so offering one would be a dead end. Note this filter applies
    to *suggestions only*: solving a premium problem elsewhere still earns a
    credit, because credit comes from the accepted-submission feed, which does
    not care what the suggestion list said.

    Args:
        problems: Candidates.
        exclude_solved: Drop problems the authenticated session has already
            solved. Meaningless without cookies (``status`` is ``None`` for
            everything), which is why the caller announces that on screen.

    Returns:
        A new list, easiest first then highest acceptance first.
    """
    kept = [
        problem
        for problem in problems
        if not problem.paid_only and not (exclude_solved and problem.solved)
    ]
    return sorted(kept, key=sort_key)
