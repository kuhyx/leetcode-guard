"""Mirror problem statements for offline reading.

The gate can fire with no network, and a lock screen listing ten problem titles
you cannot open is not much of an offer. This caches the actual text of the top
suggestions so they are readable while the connection is down.

**This is the one deliberately cuttable piece of the app.** It adds one request
per problem on top of the pool refresh -- fifty against roughly forty -- more
than doubling the API budget for a feature that only helps in the window where
you also cannot submit. If rate limiting ever appears, delete this module and
the metadata cache alone still makes the lock screen work offline.

Everything here degrades: a failed fetch caches nothing and is reported, never
raised.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING, Any, Final

from leetcode_guard._queries import STATEMENT_QUERY, statement_variables

if TYPE_CHECKING:
    from collections.abc import Sequence

    from leetcode_guard._leetcode import PostFn
    from leetcode_guard._problem import Problem

_logger: Final = logging.getLogger(__name__)

_VERSION: Final = 1
_FIELD: Final = "question"


@dataclass(frozen=True)
class Statement:
    """One problem's text, as cached."""

    title_slug: str
    title: str
    difficulty: str
    content: str
    """Raw HTML, exactly as LeetCode serves it. Rendering is the caller's
    problem; storing it verbatim keeps this module free of a parser that could
    silently lose part of a question."""


@dataclass(frozen=True)
class StatementFetch:
    """The outcome of a statement refresh."""

    statements: tuple[Statement, ...]
    attempted: int
    reason: str

    @property
    def complete(self) -> bool:
        """Whether every requested problem was retrieved."""
        return len(self.statements) == self.attempted


def parse_statement(data: object) -> Statement | None:
    """Read one ``question`` payload, or ``None`` if it is unusable.

    A premium problem returns ``content: null`` -- which is exactly why premium
    problems are excluded from the suggestion list in the first place, so
    seeing one here means the filter upstream has drifted.
    """
    if not isinstance(data, dict):
        return None
    question = data.get(_FIELD)
    if not isinstance(question, dict):
        return None
    slug = question.get("titleSlug")
    content = question.get("content")
    if not isinstance(slug, str) or not slug:
        return None
    if not isinstance(content, str) or not content:
        _logger.warning(
            "no statement content for %s -- premium problems return null here, "
            "and they should not be in the suggestion list",
            slug,
        )
        return None
    return Statement(
        title_slug=slug,
        title=str(question.get("title", slug)),
        difficulty=str(question.get("difficulty", "")),
        content=content,
    )


def fetch_statements(post: PostFn, problems: Sequence[Problem]) -> StatementFetch:
    """Retrieve the text of each problem, skipping whatever fails.

    One request per problem, sequentially. The throttle in the shared client
    paces them; parallelising would be the fastest way to earn a rate-limit
    block for a feature that is not worth one.
    """
    collected: list[Statement] = []
    failures = 0
    for problem in problems:
        result = post(STATEMENT_QUERY, statement_variables(problem.title_slug))
        if not result.ok:
            failures += 1
            _logger.warning(
                "could not fetch the statement for %s: %s",
                problem.title_slug,
                result.transport_error or "; ".join(result.errors) or "no data",
            )
            continue
        statement = parse_statement(result.data)
        if statement is None:
            failures += 1
            continue
        collected.append(statement)

    reason = (
        f"cached {len(collected)} statements"
        if not failures
        else f"cached {len(collected)} statements, {failures} unavailable"
    )
    return StatementFetch(
        statements=tuple(collected), attempted=len(problems), reason=reason
    )


def write_statements(
    path: Path, statements: Sequence[Statement], *, fetched_at: float
) -> bool:
    """Persist statements atomically.

    Returns:
        Whether the write succeeded. Never raises -- an unwritable cache is an
        inconvenience, not a reason to fail a lock.
    """
    payload: dict[str, Any] = {
        "version": _VERSION,
        "fetched_at": fetched_at,
        "statements": [
            {
                "titleSlug": item.title_slug,
                "title": item.title,
                "difficulty": item.difficulty,
                "content": item.content,
            }
            for item in statements
        ],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=path.name,
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle)
            handle.flush()
            os.fsync(handle.fileno())
            temp_name = handle.name
        Path(temp_name).replace(path)
    except OSError as exc:
        _logger.warning("could not write the statement cache to %s: %s", path, exc)
        return False
    return True


def read_statements(path: Path) -> dict[str, Statement]:
    """Load the cached statements, keyed by slug.

    Every corruption mode returns an empty mapping with a warning: an
    unreadable statement cache costs offline reading, nothing more.
    """
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _logger.warning("statement cache at %s is unreadable: %s", path, exc)
        return {}
    if not isinstance(raw, dict) or raw.get("version") != _VERSION:
        _logger.warning("statement cache at %s has an unusable shape", path)
        return {}
    rows = raw.get("statements")
    if not isinstance(rows, list):
        _logger.warning("statement cache at %s has no statements array", path)
        return {}

    cached: dict[str, Statement] = {}
    for row in rows:
        statement = parse_statement({_FIELD: row})
        if statement is None:
            _logger.warning("skipping an unreadable cached statement in %s", path)
            continue
        cached[statement.title_slug] = statement
    return cached
