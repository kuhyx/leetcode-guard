"""``recentSubmissionList``: every answer is a list or "could not check".

The shape is the one probed on 2026-11-21 (``_recent_submissions_fixtures``).
The pair that must never merge: an empty list is a real answer ("nothing
submitted lately"), ``None`` is silence.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from leetcode_guard._attempt_queries import (
    RECENT_SUBMISSIONS_LIMIT,
    RECENT_SUBMISSIONS_QUERY,
    RecentSubmission,
    fetch_recent_submissions,
    recent_submissions_variables,
)
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard.tests._net_fixtures import fake_post
from leetcode_guard.tests._recent_submissions_fixtures import (
    MAX_ROWS,
    ROW_KEYS,
    recent_submission_row,
    recent_submissions_result,
)

if TYPE_CHECKING:
    from leetcode_guard._leetcode import PostFn


def fetch(*results: GraphQLResult) -> list[RecentSubmission] | None:
    """Fetch for user ``k`` through a scripted fake."""
    post: PostFn = fake_post(*results)
    return fetch_recent_submissions(post, "k")


def test_the_query_asks_for_exactly_the_probed_keys():
    """Each key of the fixture row is selected, and nothing else."""
    body = RECENT_SUBMISSIONS_QUERY.split("recentSubmissionList", 1)[1]
    selected = set(body.split("{", 1)[1].split("}", 1)[0].split())

    assert selected == ROW_KEYS
    assert body.startswith("(username: $username, limit: $limit)")


def test_the_variables_carry_the_username_and_the_server_cap():
    """The page limit is the 20 the server enforces anyway."""
    assert recent_submissions_variables("k") == {"username": "k", "limit": MAX_ROWS}
    assert MAX_ROWS == RECENT_SUBMISSIONS_LIMIT


def test_every_status_is_kept_not_only_accepted():
    """The point of this query over the accepted-only one."""
    rows = [
        recent_submission_row("1", "two-sum", status="Wrong Answer", timestamp=100),
        recent_submission_row("2", "two-sum", status="Accepted", timestamp=200),
    ]

    assert fetch(recent_submissions_result(rows)) == [
        RecentSubmission("1", "two-sum", "Wrong Answer", 100),
        RecentSubmission("2", "two-sum", "Accepted", 200),
    ]


def test_an_empty_list_is_an_answer_not_silence():
    """Nothing submitted lately is a real answer, and it is not ``None``."""
    assert fetch(recent_submissions_result([])) == []


@pytest.mark.parametrize(
    "result",
    [
        GraphQLResult(transport_error="boom"),
        GraphQLResult(errors=("That user does not exist.",)),
        GraphQLResult(),
        GraphQLResult(data={}),
        GraphQLResult(data={"recentSubmissionList": None}),
        GraphQLResult(data={"recentSubmissionList": "oops"}),
    ],
    ids=[
        "transport",
        "graphql-error",
        "no-data",
        "no-field",
        "null-list",
        "not-a-list",
    ],
)
def test_every_failure_is_could_not_check_never_an_empty_list(
    result: GraphQLResult, caplog: pytest.LogCaptureFixture
):
    """HTTP 200 with a null payload looks like "no submissions"; it is not."""
    with caplog.at_level(logging.WARNING):
        assert fetch(result) is None

    assert "recentSubmissionList" in caplog.text


def test_malformed_rows_are_dropped_and_only_counted(
    caplog: pytest.LogCaptureFixture,
):
    """A bad row costs itself; the log has the count, never the row's content."""
    good = recent_submission_row("7", "two-sum", status="Accepted", timestamp=5)
    bad: list[object] = [
        "not an object",
        {**good, "id": None},
        {**good, "id": ""},
        {**good, "titleSlug": ""},
        {**good, "titleSlug": 3},
        {**good, "statusDisplay": ""},
        {**good, "statusDisplay": None},
        {**good, "timestamp": "12.5"},
        {**good, "timestamp": "-3"},
        {**good, "timestamp": None},
        {**good, "timestamp": True},
        {**good, "timestamp": "٣"},
    ]

    with caplog.at_level(logging.WARNING):
        rows = fetch(recent_submissions_result([*bad, good]))

    assert rows == [RecentSubmission("7", "two-sum", "Accepted", 5)]
    assert f"dropped {len(bad)} malformed" in caplog.text
    assert "not an object" not in caplog.text


def test_a_numeric_id_and_timestamp_are_coerced():
    """The id may arrive as a number and the timestamp as an int; both are fine."""
    row = {**recent_submission_row("1", "two-sum"), "id": 99, "timestamp": 7}

    assert fetch(recent_submissions_result([row])) == [
        RecentSubmission("99", "two-sum", "Wrong Answer", 7)
    ]


def test_a_clean_page_logs_nothing(caplog: pytest.LogCaptureFixture):
    """No malformed rows, no warning."""
    with caplog.at_level(logging.WARNING):
        fetch(recent_submissions_result([recent_submission_row("1", "two-sum")]))

    assert not caplog.records
