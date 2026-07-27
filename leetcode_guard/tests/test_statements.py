"""Tests for the offline statement mirror."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import pytest

from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._problem import Problem, parse_problem
from leetcode_guard._statements import (
    Statement,
    fetch_statements,
    parse_statement,
    read_statements,
    write_statements,
)
from leetcode_guard.tests._net_fixtures import fake_post, problem_row

if TYPE_CHECKING:
    from pathlib import Path


def problem(slug: str) -> Problem:
    parsed = parse_problem(problem_row(slug))
    assert parsed is not None
    return parsed


def statement_result(slug: str, content: str = "<p>Do the thing.</p>") -> GraphQLResult:
    return GraphQLResult(
        data={
            "question": {
                "titleSlug": slug,
                "title": slug.replace("-", " ").title(),
                "difficulty": "Easy",
                "content": content,
            }
        }
    )


def test_a_statement_is_fetched_and_parsed():
    post = fake_post(statement_result("two-sum"))

    fetched = fetch_statements(post, [problem("two-sum")])

    assert fetched.complete
    assert fetched.statements[0].title_slug == "two-sum"
    assert "Do the thing" in fetched.statements[0].content
    assert post.calls[0][1] == {"titleSlug": "two-sum"}


def test_one_request_per_problem():
    """Sequential and paced. Parallelising fifty requests is the fastest way to
    earn a rate-limit block for a feature not worth one."""
    post = fake_post(statement_result("a"))

    fetch_statements(post, [problem("a"), problem("b"), problem("c")])

    assert len(post.calls) == 3


def test_a_failed_fetch_is_skipped_not_fatal():
    post = fake_post(
        statement_result("good"),
        GraphQLResult(transport_error="down"),
    )

    fetched = fetch_statements(post, [problem("good"), problem("bad")])

    assert not fetched.complete
    assert [s.title_slug for s in fetched.statements] == ["good"]
    assert "1 unavailable" in fetched.reason


def test_a_premium_problem_returns_no_content_and_is_logged(caplog):
    """content: null is exactly why premium problems are filtered upstream, so
    seeing one here means that filter has drifted."""
    post = fake_post(statement_result("premium", content=""))

    with caplog.at_level(logging.WARNING):
        fetched = fetch_statements(post, [problem("premium")])

    assert fetched.statements == ()
    assert any("premium problems return null" in r.message for r in caplog.records)


def test_an_empty_request_list_is_complete_and_free():
    post = fake_post(statement_result("x"))

    fetched = fetch_statements(post, [])

    assert fetched.complete
    assert post.calls == []
    assert "cached 0 statements" in fetched.reason


@pytest.mark.parametrize(
    "payload",
    [
        "not-an-object",
        {},
        {"question": "not-an-object"},
        {"question": {"content": "x"}},
        {"question": {"titleSlug": "", "content": "x"}},
        {"question": {"titleSlug": "s"}},
        {"question": {"titleSlug": "s", "content": 7}},
    ],
)
def test_unusable_payloads_parse_to_none(payload: Any):
    assert parse_statement(payload) is None


def test_the_title_falls_back_to_the_slug():
    parsed = parse_statement({"question": {"titleSlug": "two-sum", "content": "x"}})

    assert parsed is not None
    assert parsed.title == "two-sum"
    assert parsed.difficulty == ""


def test_round_trip_through_disk(tmp_path: Path):
    path = tmp_path / "statements.json"
    statements = (
        Statement("two-sum", "Two Sum", "Easy", "<p>a</p>"),
        Statement("add-two", "Add Two", "Medium", "<p>b</p>"),
    )

    assert write_statements(path, statements, fetched_at=1000.0)
    loaded = read_statements(path)

    assert set(loaded) == {"two-sum", "add-two"}
    assert loaded["two-sum"].content == "<p>a</p>"
    assert loaded["add-two"].difficulty == "Medium"


def test_writing_creates_the_parent_directory(tmp_path: Path):
    path = tmp_path / "nested" / "statements.json"

    assert write_statements(path, (), fetched_at=0.0)
    assert path.exists()


def test_a_failed_write_is_reported_not_raised(tmp_path: Path):
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")

    assert not write_statements(blocker / "statements.json", (), fetched_at=0.0)


def test_a_missing_cache_reads_empty(tmp_path: Path):
    assert read_statements(tmp_path / "absent.json") == {}


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '["a"]',
        '{"version": 99, "statements": []}',
        '{"version": 1}',
        '{"version": 1, "statements": "nope"}',
    ],
)
def test_every_corruption_mode_reads_empty(tmp_path: Path, content: str):
    path = tmp_path / "statements.json"
    path.write_text(content, encoding="utf-8")

    assert read_statements(path) == {}


def test_an_unreadable_cache_path_reads_empty(tmp_path: Path):
    path = tmp_path / "statements.json"
    path.mkdir()

    assert read_statements(path) == {}


def test_a_corrupt_row_is_skipped_not_fatal(tmp_path: Path, caplog):
    path = tmp_path / "statements.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "fetched_at": 1.0,
                "statements": [
                    {
                        "titleSlug": "kept",
                        "title": "Kept",
                        "difficulty": "Easy",
                        "content": "x",
                    },
                    {"nope": True},
                ],
            }
        ),
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        loaded = read_statements(path)

    assert set(loaded) == {"kept"}
