"""Tests for problem parsing and the suggestion ordering."""

from __future__ import annotations

import pytest

from leetcode_guard._problem import (
    Problem,
    page_row_count,
    page_total,
    parse_problem,
    parse_questions,
    rank_pool,
    sort_key,
)
from leetcode_guard.tests._net_fixtures import problem_row


def make(slug: str, **kwargs: object) -> Problem:
    row = problem_row(slug, **kwargs)
    parsed = parse_problem(row)
    assert parsed is not None
    return parsed


def test_parses_a_full_row():
    problem = make(
        "two-sum", difficulty="Easy", ac_rate=57.9, topics=["array", "hash-table"]
    )

    assert problem.title_slug == "two-sum"
    assert problem.ac_rate == pytest.approx(57.9)
    assert problem.topics == ("array", "hash-table")
    assert problem.url == "https://leetcode.com/problems/two-sum/"
    assert not problem.solved


def test_status_ac_means_solved():
    assert make("two-sum", status="ac").solved
    assert not make("two-sum", status="notac").solved
    assert not make("two-sum", status=None).solved


@pytest.mark.parametrize(
    "row",
    [
        "not-an-object",
        {"acRate": 1.0, "difficulty": "Easy"},
        {"titleSlug": "", "acRate": 1.0, "difficulty": "Easy"},
        {"titleSlug": "s", "difficulty": "Easy"},
        {"titleSlug": "s", "acRate": "high", "difficulty": "Easy"},
        {"titleSlug": "s", "acRate": True, "difficulty": "Easy"},
        {"titleSlug": "s", "acRate": 1.0},
        {"titleSlug": "s", "acRate": 1.0, "difficulty": 3},
    ],
)
def test_unusable_rows_are_rejected(row: object):
    assert parse_problem(row) is None


def test_integer_ac_rate_is_accepted():
    parsed = parse_problem({"titleSlug": "s", "acRate": 50, "difficulty": "Easy"})

    assert parsed is not None
    assert parsed.ac_rate == 50.0


def test_non_string_status_becomes_none():
    parsed = parse_problem(
        {"titleSlug": "s", "acRate": 1.0, "difficulty": "Easy", "status": 7}
    )

    assert parsed is not None
    assert parsed.status is None


@pytest.mark.parametrize(
    "tags", ["not-a-list", None, [{"name": "x"}, "junk", {"slug": 5}]]
)
def test_malformed_topic_tags_degrade_to_empty(tags: object):
    parsed = parse_problem(
        {"titleSlug": "s", "acRate": 1.0, "difficulty": "Easy", "topicTags": tags}
    )

    assert parsed is not None
    assert parsed.topics == ()


def test_title_defaults_to_the_slug():
    parsed = parse_problem(
        {"titleSlug": "some-slug", "acRate": 1.0, "difficulty": "Easy"}
    )

    assert parsed is not None
    assert parsed.title == "some-slug"


@pytest.mark.parametrize("page", ["not-an-object", {"questions": "not-a-list"}, {}])
def test_malformed_pages_yield_no_problems(page: object):
    assert parse_questions(page) == []
    assert page_row_count(page) == 0


def test_page_row_count_counts_rows_not_parsed_problems():
    """The pager advances by this number. Counting parsed problems instead
    would shift every later page whenever one row was malformed."""
    page = {"questions": [problem_row("good"), "junk"]}

    assert page_row_count(page) == 2
    assert len(parse_questions(page)) == 1


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        ({"total": 4003}, 4003),
        ({"total": True}, None),
        ({"total": "4003"}, None),
        ({}, None),
        ("x", None),
    ],
)
def test_page_total(page: object, expected: int | None):
    assert page_total(page) == expected


def test_ordering_is_easiest_first_then_highest_acceptance():
    problems = [
        make("hard-high", difficulty="Hard", ac_rate=99.0),
        make("easy-low", difficulty="Easy", ac_rate=10.0),
        make("medium-mid", difficulty="Medium", ac_rate=50.0),
        make("easy-high", difficulty="Easy", ac_rate=90.0),
    ]

    ranked = rank_pool(problems, exclude_solved=False)

    assert [item.title_slug for item in ranked] == [
        "easy-high",
        "easy-low",
        "medium-mid",
        "hard-high",
    ]


def test_unknown_difficulty_sorts_last_rather_than_first():
    unknown = make("mystery", difficulty="Impossible", ac_rate=100.0)
    easy = make("easy", difficulty="Easy", ac_rate=1.0)

    ranked = rank_pool([unknown, easy], exclude_solved=False)

    assert [item.title_slug for item in ranked] == ["easy", "mystery"]
    assert sort_key(unknown)[0] == 3


def test_premium_problems_are_always_dropped_from_suggestions():
    premium = make("premium", paid_only=True, ac_rate=99.0)
    free = make("free", ac_rate=1.0)

    ranked = rank_pool([premium, free], exclude_solved=False)

    assert [item.title_slug for item in ranked] == ["free"]


def test_solved_problems_are_dropped_only_when_requested():
    solved = make("solved", status="ac", ac_rate=99.0)
    unsolved = make("unsolved", status="notac", ac_rate=1.0)

    assert [
        p.title_slug for p in rank_pool([solved, unsolved], exclude_solved=True)
    ] == ["unsolved"]
    assert [
        p.title_slug for p in rank_pool([solved, unsolved], exclude_solved=False)
    ] == [
        "solved",
        "unsolved",
    ]
