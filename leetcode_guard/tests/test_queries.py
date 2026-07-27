"""Tests for the GraphQL documents and their variable builders.

Shape assertions, not round-trips: introspection is disabled on the endpoint,
so these strings cannot be validated against a schema. What can be pinned is
that the documents still ask for the fields the parsers require, and that the
traps recorded in the module docstring have not crept back in.
"""

from __future__ import annotations

from leetcode_guard._constants import RECENT_AC_LIMIT
from leetcode_guard._queries import (
    POOL_QUERY,
    RECENT_AC_QUERY,
    STATEMENT_QUERY,
    pool_variables,
    recent_ac_variables,
    statement_variables,
)


def test_pool_query_requests_every_field_the_parser_reads():
    for field in (
        "titleSlug",
        "difficulty",
        "acRate",
        "isPaidOnly",
        "status",
        "topicTags",
    ):
        assert field in POOL_QUERY


def test_pool_query_has_no_sort_argument():
    """``sortBy`` is not a valid argument on ``questionList`` -- the endpoint
    rejects the whole document. Ordering is local, and must stay local."""
    assert "sortBy" not in POOL_QUERY


def test_pool_query_takes_no_inline_difficulty_literal():
    """An inline ``difficulty: "EASY"`` fails type checking against
    ``DifficultyEnum``; it only works as a typed variable."""
    assert "DifficultyEnum" not in POOL_QUERY
    assert "filters: {}" in POOL_QUERY


def test_recent_ac_query_requests_the_id_the_ledger_keys_on():
    assert "id" in RECENT_AC_QUERY
    assert "timestamp" in RECENT_AC_QUERY
    assert "titleSlug" in RECENT_AC_QUERY


def test_statement_query_requests_content():
    assert "content" in STATEMENT_QUERY


def test_pool_variables():
    assert pool_variables(skip=200, limit=100) == {"skip": 200, "limit": 100}


def test_recent_ac_variables_pin_the_server_cap():
    variables = recent_ac_variables("kuchy")

    assert variables == {"username": "kuchy", "limit": RECENT_AC_LIMIT}
    assert RECENT_AC_LIMIT == 20


def test_statement_variables():
    assert statement_variables("two-sum") == {"titleSlug": "two-sum"}
