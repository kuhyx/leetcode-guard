"""The solved-count mirror: parsing, caching, and the three-valued fetch."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _progress
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._progress import (
    Progress,
    fetch_progress,
    parse_progress,
    read_progress_cache,
    refresh_progress,
    write_progress_cache,
)
from leetcode_guard._queries import PROGRESS_QUERY
from leetcode_guard.tests._net_fixtures import fake_post

if TYPE_CHECKING:
    from pathlib import Path


def counts(easy: int, medium: int, hard: int) -> list[dict[str, object]]:
    """The wire shape, with the ``All`` row LeetCode also sends."""
    return [
        {"difficulty": "All", "count": easy + medium + hard},
        {"difficulty": "Easy", "count": easy},
        {"difficulty": "Medium", "count": medium},
        {"difficulty": "Hard", "count": hard},
    ]


def payload(solved=(55, 0, 0), total=(965, 2115, 975)) -> dict[str, object]:
    """A healthy ``PROGRESS_QUERY`` answer, as measured on 2026-09-19."""
    return {
        "allQuestionsCount": counts(*total),
        "matchedUser": {"submitStatsGlobal": {"acSubmissionNum": counts(*solved)}},
    }


def a_progress(fetched_at: float = 1000.0) -> Progress:
    return Progress(
        solved={"Easy": 55, "Medium": 0, "Hard": 0},
        total={"Easy": 965, "Medium": 2115, "Hard": 975},
        fetched_at=fetched_at,
    )


def test_a_healthy_payload_parses_and_ignores_the_all_row():
    progress = parse_progress(payload(), fetched_at=7.0)

    assert progress == a_progress(7.0)
    assert progress.solved_all == 55
    assert progress.total_all == 4055
    assert progress.remaining("Easy") == 910


def test_remaining_never_goes_negative():
    progress = Progress(
        solved={"Easy": 9, "Medium": 0, "Hard": 0},
        total={"Easy": 5, "Medium": 0, "Hard": 0},
        fetched_at=0.0,
    )
    assert progress.remaining("Easy") == 0


def test_an_unknown_user_is_unreadable_even_with_a_healthy_denominator():
    """The measured shape: counts present, ``matchedUser: null``. Not zero."""
    data = payload()
    data["matchedUser"] = None

    assert parse_progress(data, fetched_at=0.0) is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.__setitem__("allQuestionsCount", "not a list"),
        lambda d: d["allQuestionsCount"].pop(1),
        lambda d: d["allQuestionsCount"].__setitem__(1, "junk"),
        lambda d: d["allQuestionsCount"][1].__setitem__("count", True),
        lambda d: d["allQuestionsCount"][1].__setitem__("count", "5"),
        lambda d: d.__setitem__("matchedUser", {"submitStatsGlobal": "x"}),
        lambda d: d.__setitem__("matchedUser", {"submitStatsGlobal": {}}),
    ],
)
def test_a_partial_payload_is_unreadable_rather_than_wrong(mutate):
    data = payload()
    mutate(data)

    assert parse_progress(data, fetched_at=0.0) is None


def test_a_non_object_payload_is_unreadable():
    assert parse_progress(["nope"], fetched_at=0.0) is None


def test_fetch_asks_the_progress_query_for_the_username():
    post = fake_post(GraphQLResult(data=payload()))

    progress = fetch_progress(post, "kuchy", now=3.0)

    assert progress == a_progress(3.0)
    assert post.calls == [(PROGRESS_QUERY, {"username": "kuchy"})]


@pytest.mark.parametrize(
    ("result", "phrase"),
    [
        (GraphQLResult(transport_error="socket closed"), "socket closed"),
        (GraphQLResult(data={}, errors=("That user does not exist.",)), "not exist"),
        (GraphQLResult(data=None), "null payload"),
    ],
)
def test_every_failed_fetch_is_none_and_logged(result, phrase, caplog):
    with caplog.at_level("WARNING"):
        assert fetch_progress(fake_post(result), "kuchy", now=0.0) is None

    assert phrase in caplog.text


def test_an_unreadable_answer_is_none_and_logged(caplog):
    with caplog.at_level("WARNING"):
        assert fetch_progress(fake_post(GraphQLResult(data={})), "k", now=0.0) is None

    assert "unreadable" in caplog.text


def test_the_cache_round_trips(tmp_path: Path):
    path = tmp_path / "progress_cache.json"

    assert write_progress_cache(path, a_progress(42.0))
    assert read_progress_cache(path) == a_progress(42.0)


def test_a_missing_cache_is_none(tmp_path: Path):
    assert read_progress_cache(tmp_path / "absent.json") is None


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        "[]",
        json.dumps({"version": 99}),
        json.dumps({"version": 1, "fetched_at": "yesterday"}),
        json.dumps({"version": 1, "fetched_at": True}),
        json.dumps({"version": 1, "fetched_at": 1.0, "solved": "x", "total": {}}),
        json.dumps(
            {
                "version": 1,
                "fetched_at": 1.0,
                "solved": {"Easy": 1, "Medium": 1},
                "total": {"Easy": 1, "Medium": 1, "Hard": 1},
            }
        ),
        json.dumps(
            {
                "version": 1,
                "fetched_at": 1.0,
                "solved": {"Easy": True, "Medium": 1, "Hard": 1},
                "total": {"Easy": 1, "Medium": 1, "Hard": 1},
            }
        ),
    ],
)
def test_a_corrupt_cache_is_none_and_logged(tmp_path: Path, content: str, caplog):
    path = tmp_path / "progress_cache.json"
    path.write_text(content, encoding="utf-8")

    with caplog.at_level("WARNING"):
        assert read_progress_cache(path) is None

    assert "progress cache" in caplog.text


def test_a_failed_write_is_false_and_logged(tmp_path: Path, monkeypatch, caplog):
    def refuse(*_args, **_kwargs):
        msg = "disk full"
        raise OSError(msg)

    monkeypatch.setattr(_progress, "write_json", refuse)

    with caplog.at_level("WARNING"):
        assert not write_progress_cache(tmp_path / "p.json", a_progress())

    assert "disk full" in caplog.text


def test_refresh_writes_the_fresh_answer(tmp_path: Path):
    path = tmp_path / "progress_cache.json"

    fresh = refresh_progress(
        fake_post(GraphQLResult(data=payload())), "k", path, now=9.0
    )

    assert fresh == a_progress(9.0)
    assert read_progress_cache(path) == a_progress(9.0)


def test_refresh_falls_back_to_the_cache_when_the_fetch_fails(tmp_path: Path):
    path = tmp_path / "progress_cache.json"
    write_progress_cache(path, a_progress(1.0))

    stale = refresh_progress(
        fake_post(GraphQLResult(transport_error="offline")), "k", path, now=9.0
    )

    assert stale == a_progress(1.0)
