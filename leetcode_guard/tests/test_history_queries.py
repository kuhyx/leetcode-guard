"""``questionSubmissionList`` / ``submissionDetails``: a page, code, or silence.

Row shape as measured 2026-11-22 (``_history_queries`` docstring). ``None`` is
"could not check" and must never read as "no submissions".
"""

from __future__ import annotations

import logging

import pytest

from leetcode_guard._history_queries import (
    PAGE_SIZE,
    HistoryPage,
    HistoryRow,
    fetch_code,
    fetch_page,
)
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard.tests._net_fixtures import fake_post

LIVE_ROW = {
    "id": "1834567890",
    "statusDisplay": "Wrong Answer",
    "lang": "python3",
    "timestamp": "1795287000",
    "runtime": "N/A",
    "memory": "N/A",
}


def page_result(rows: list[object], *, has_next: bool = False) -> GraphQLResult:
    """A ``questionSubmissionList`` answer."""
    block = {"hasNext": has_next, "submissions": rows}
    return GraphQLResult(data={"questionSubmissionList": block})


def test_a_page_parses_every_status_and_asks_for_the_slug_and_offset():
    """The variables carry the slug, the offset and the server's page size."""
    post = fake_post(page_result([LIVE_ROW], has_next=True))

    page = fetch_page(post, "two-sum", 20)

    row = HistoryRow("1834567890", "Wrong Answer", "python3", 1795287000, "N/A", "N/A")
    assert page == HistoryPage((row,), has_next=True)
    assert post.calls[0][1] == {
        "offset": 20,
        "limit": PAGE_SIZE,
        "questionSlug": "two-sum",
    }


@pytest.mark.parametrize(
    "result",
    [
        GraphQLResult(transport_error="timeout"),
        GraphQLResult(errors=("rate limited",)),
        GraphQLResult(data=None),
        GraphQLResult(data={"questionSubmissionList": None}),
        GraphQLResult(data={"questionSubmissionList": {"submissions": None}}),
    ],
    ids=["transport", "graphql", "null-data", "null-list", "null-rows"],
)
def test_silence_is_could_not_check(
    result: GraphQLResult, caplog: pytest.LogCaptureFixture
):
    """Every unreadable answer is ``None``, logged at warning."""
    with caplog.at_level(logging.WARNING):
        assert fetch_page(fake_post(result), "two-sum", 0) is None
    assert caplog.records


def test_an_empty_page_is_an_answer():
    """No submissions on this problem is a real answer, not silence."""
    assert fetch_page(fake_post(page_result([])), "x", 0) == HistoryPage(
        (), has_next=False
    )


@pytest.mark.parametrize(
    "bad",
    [
        "not a dict",
        {**LIVE_ROW, "id": "abc"},
        {**LIVE_ROW, "statusDisplay": ""},
        {**LIVE_ROW, "timestamp": "soon"},
        {**LIVE_ROW, "timestamp": 1795287000},
    ],
    ids=["type", "id", "status", "stamp-text", "stamp-int"],
)
def test_a_malformed_row_is_dropped_and_logged(
    bad: object, caplog: pytest.LogCaptureFixture
):
    """One bad row costs itself, never the page."""
    with caplog.at_level(logging.WARNING):
        page = fetch_page(fake_post(page_result([bad, LIVE_ROW])), "x", 0)

    assert page is not None
    assert [row.submission_id for row in page.rows] == ["1834567890"]
    assert "dropped 1 malformed" in caplog.text


def test_missing_optional_fields_read_as_blank():
    """``lang``/``runtime``/``memory`` are display text; absent is blank."""
    row = {key: LIVE_ROW[key] for key in ("id", "statusDisplay", "timestamp")}

    page = fetch_page(fake_post(page_result([row])), "x", 0)

    assert page is not None
    assert (page.rows[0].lang, page.rows[0].runtime, page.rows[0].memory) == (
        "",
        "",
        "",
    )


def test_code_is_read_by_integer_id():
    """``submissionDetails`` takes an Int id and returns the code."""
    post = fake_post(
        GraphQLResult(data={"submissionDetails": {"code": "class S: ..."}})
    )

    assert fetch_code(post, "42") == "class S: ..."
    assert post.calls[0][1] == {"submissionId": 42}


@pytest.mark.parametrize(
    "result",
    [
        GraphQLResult(data={"submissionDetails": None}),
        GraphQLResult(data={"submissionDetails": {"code": None}}),
        GraphQLResult(errors=("nope",)),
    ],
    ids=["null", "null-code", "error"],
)
def test_unreadable_code_is_none(result: GraphQLResult):
    """Silence again: the caller counts a failed read and retries later."""
    assert fetch_code(fake_post(result), "42") is None
