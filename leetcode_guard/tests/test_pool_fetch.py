"""Tests for the pool pager.

The regression that matters here: LeetCode caps a page at 100 rows without
saying so, and an earlier pager advanced ``skip`` by the *requested* size. It
collected 657 of 4003 problems and reported success.
"""

from __future__ import annotations

from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._pool_fetch import fetch_pool
from leetcode_guard.tests._net_fixtures import (
    fake_post,
    null_data_result,
    pool_result,
    problem_row,
)


def rows(count: int, *, start: int = 0) -> list[dict]:
    return [problem_row(f"problem-{index}") for index in range(start, start + count)]


def test_advances_by_rows_returned_not_by_requested_page_size():
    """Ask for 100, get 40, and the next skip must be 40 -- not 100."""
    post = fake_post(
        pool_result(rows(40), total=100),
        pool_result(rows(40, start=40), total=100),
        pool_result(rows(20, start=80), total=100),
        pool_result([], total=100),
    )

    result = fetch_pool(post, page_size=100, max_pages=10)

    assert result.complete
    assert len(result.problems) == 100
    assert [call[1]["skip"] for call in post.calls] == [0, 40, 80]


def test_stops_once_the_advertised_total_is_reached():
    post = fake_post(pool_result(rows(50), total=50))

    result = fetch_pool(post, page_size=100, max_pages=10)

    assert result.complete
    assert "fetched all 50 problems" in result.reason
    assert len(post.calls) == 1


def test_stops_on_an_empty_page_when_no_total_was_advertised():
    post = fake_post(pool_result(rows(10)), pool_result([]))

    result = fetch_pool(post, page_size=100, max_pages=10)

    assert result.complete
    assert result.total is None
    assert "reached the end" in result.reason
    assert len(result.problems) == 10


def test_transport_failure_returns_a_partial_pool():
    post = fake_post(
        pool_result(rows(10), total=100),
        GraphQLResult(transport_error="connection reset"),
    )

    result = fetch_pool(post, page_size=100, max_pages=10)

    assert not result.complete
    assert len(result.problems) == 10
    assert "connection reset" in result.reason


def test_graphql_errors_return_a_partial_pool():
    post = fake_post(GraphQLResult(errors=("Rate limited", "Try later")))

    result = fetch_pool(post, page_size=100, max_pages=10)

    assert not result.complete
    assert result.problems == ()
    assert "Rate limited; Try later" in result.reason


def test_null_data_returns_a_partial_pool():
    post = fake_post(null_data_result())

    result = fetch_pool(post, page_size=100, max_pages=10)

    assert not result.complete
    assert "no data" in result.reason


def test_page_guard_stops_a_pager_that_never_finishes():
    """A server that keeps returning full pages past the advertised total must
    not spin forever."""
    post = fake_post(pool_result(rows(10)))

    result = fetch_pool(post, page_size=10, max_pages=3)

    assert not result.complete
    assert "3-page guard" in result.reason
    assert len(post.calls) == 3


def test_malformed_rows_are_dropped_but_do_not_shift_the_pager():
    post = fake_post(
        pool_result([problem_row("good"), "junk"], total=2),
        pool_result([], total=2),
    )

    result = fetch_pool(post, page_size=100, max_pages=10)

    assert [item.title_slug for item in result.problems] == ["good"]
    assert result.complete
