"""Fakes for the network seam.

Every module above :mod:`leetcode_guard._leetcode` takes a ``PostFn``, so the
whole suite mocks exactly one thing: a two-argument function returning a
:class:`GraphQLResult`. There is no HTTP mocking library anywhere, and only
``test_leetcode.py`` ever patches ``requests``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

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


def problem_row(
    slug: str,
    *,
    difficulty: str = "Easy",
    ac_rate: float = 50.0,
    paid_only: bool = False,
    status: str | None = None,
    frontend_id: str = "1",
    topics: Sequence[str] = (),
) -> dict[str, Any]:
    """One row shaped exactly like the live ``questions`` array."""
    return {
        "frontendQuestionId": frontend_id,
        "title": slug.replace("-", " ").title(),
        "titleSlug": slug,
        "difficulty": difficulty,
        "acRate": ac_rate,
        "paidOnly": paid_only,
        "status": status,
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

    A ``None`` status is what a signed-out or expired session receives -- the
    request succeeds and the payload is well formed, which is exactly why it
    has to be distinguishable from "not solved".
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
