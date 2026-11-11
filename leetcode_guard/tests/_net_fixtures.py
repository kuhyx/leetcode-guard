"""Fakes for the network seam.

Every module above :mod:`leetcode_guard._leetcode` takes a ``PostFn``, so the
whole suite mocks exactly one thing: a two-argument function returning a
:class:`GraphQLResult`. There is no HTTP mocking library anywhere, and only
``test_leetcode.py`` ever patches ``requests``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, TypedDict, Unpack

from leetcode_guard._leetcode import GraphQLResult

PostCall = tuple[str, dict[str, Any]]


class FakePost:
    """A scripted ``PostFn`` that records what it was asked."""

    def __init__(self, results: Sequence[GraphQLResult]) -> None:
        self._results = list(results)
        self.calls: list[PostCall] = []

    def __call__(self, query: str, variables: dict[str, Any]) -> GraphQLResult:
        self.calls.append((query, dict(variables)))
        if not self._results:
            return GraphQLResult(transport_error="fake ran out of scripted results")
        if len(self._results) == 1:
            return self._results[0]
        return self._results.pop(0)


def fake_post(*results: GraphQLResult) -> FakePost:
    """Script a sequence of responses.

    The final entry repeats forever, so a pager that keeps asking gets a stable
    answer rather than a confusing "ran out" error.
    """
    return FakePost(results)


class RowOptions(TypedDict, total=False):
    """The keyword options :func:`problem_row` takes; all are optional."""

    difficulty: str
    ac_rate: float
    paid_only: bool
    status: str | None
    frontend_id: str
    topics: Sequence[str]


def problem_row(slug: str, **options: Unpack[RowOptions]) -> dict[str, Any]:
    """One row shaped exactly like the live ``questions`` array.

    Defaults: ``Easy``, 50% acceptance, free, never attempted, id ``"1"``,
    no topics.
    """
    topics = options.get("topics", ())
    return {
        "frontendQuestionId": options.get("frontend_id", "1"),
        "title": slug.replace("-", " ").title(),
        "titleSlug": slug,
        "difficulty": options.get("difficulty", "Easy"),
        "acRate": options.get("ac_rate", 50.0),
        "paidOnly": options.get("paid_only", False),
        "status": options.get("status"),
        "topicTags": [{"name": topic.title(), "slug": topic} for topic in topics],
    }


def pool_result(
    rows: Sequence[dict[str, Any]], *, total: int | None = None
) -> GraphQLResult:
    """Wrap problem rows in a ``problemsetQuestionList`` envelope."""
    page: dict[str, Any] = {"questions": list(rows)}
    if total is not None:
        page["total"] = total
    return GraphQLResult(data={"problemsetQuestionList": page})


def status_result(slug: str, status: str | None) -> GraphQLResult:
    """Wrap one problem's solved-state in a ``question`` envelope.

    Run against the live endpoint on 2026-08-14 with a working session, and
    these are the three values it actually returned, not what was inferred
    from a broken one:

    * ``"ac"`` -- solved.
    * ``"notac"`` -- attempted, with a failed submission on record.
    * ``None`` -- **never attempted**. Also what an expired session returns for
      every problem, which is why a null alone cannot tell the two apart.

    This docstring previously claimed a null meant "signed out or expired",
    inferred from a dead cookie where everything is null. Tests written from
    that premise passed while the code shipped the same error -- see
    ``scripts/verify_solved_semantics.py``, which checks it against the real
    endpoint because a fixture can only ever repeat what its author believed.
    """
    return GraphQLResult(data={"question": {"titleSlug": slug, "status": status}})


def submission_row(
    submission_id: str,
    slug: str,
    *,
    timestamp: int = 1_700_000_000,
    lang: str = "python3",
) -> dict[str, Any]:
    """One row shaped exactly like the live ``recentAcSubmissionList`` array."""
    return {
        "id": submission_id,
        "title": slug.replace("-", " ").title(),
        "titleSlug": slug,
        "timestamp": str(timestamp),
        "lang": lang,
        "langName": lang.title(),
        "statusDisplay": "Accepted",
    }


def recent_ac_result(rows: Sequence[dict[str, Any]]) -> GraphQLResult:
    """Wrap submission rows in their envelope."""
    return GraphQLResult(data={"recentAcSubmissionList": list(rows)})


def null_data_result() -> GraphQLResult:
    """What an expired session looks like: HTTP 200, no payload, no error."""
    return GraphQLResult()


PostFactory = Callable[..., FakePost]
