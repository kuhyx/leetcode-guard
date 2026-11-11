"""A problem LeetCode never resolves is retried once a day, not every tick."""

from __future__ import annotations

from datetime import timedelta
import json
import logging
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _constants, _difficulty_negative
from leetcode_guard._difficulty import load_weights
from leetcode_guard._difficulty_negative import (
    RETRY_SECONDS,
    is_backed_off,
    load_unresolved,
    save_unresolved,
)
from leetcode_guard._difficulty_resolve import resolve_difficulties, resolve_probe
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard.tests._difficulty_fixtures import question_result, seed_pool
from leetcode_guard.tests._guard_factories import probe_of
from leetcode_guard.tests._ledger_fixtures import NOW
from leetcode_guard.tests._net_fixtures import fake_post

if TYPE_CHECKING:
    from pathlib import Path

DELETED = GraphQLResult(data={"question": None})
DAY = timedelta(seconds=RETRY_SECONDS)


@pytest.mark.usefixtures("data_dir")
def test_a_deleted_problem_is_asked_once_per_day(hmac_key: Path):
    """A slug LeetCode cannot resolve is asked again only after a day."""
    post = fake_post(DELETED)
    for minutes in (0, 1, 2, 600):
        resolve_difficulties(
            ["gone"],
            post=post,
            now=NOW + timedelta(minutes=minutes),
            key_file=hmac_key,
        )
    assert len(post.calls) == 1

    again = resolve_difficulties(["gone"], post=post, now=NOW + DAY, key_file=hmac_key)

    assert len(post.calls) == 2
    assert again.fetched == 1


@pytest.mark.usefixtures("data_dir")
def test_backoff_is_not_a_failure_and_costs_no_fetch_budget(hmac_key: Path):
    """A backed-off slug is neither a failure nor a use of max_fetch."""
    first = fake_post(DELETED)
    resolve_difficulties(["gone"], post=first, now=NOW, key_file=hmac_key)
    post = fake_post(question_result("Hard"))

    result = resolve_difficulties(
        ["gone", "fresh"], post=post, now=NOW, key_file=hmac_key, max_fetch=1
    )

    assert (result.backed_off, result.failed, result.fetched) == (1, 0, 1)
    assert post.calls[0][1] == {"titleSlug": "fresh"}


@pytest.mark.usefixtures("data_dir")
def test_an_unresolved_problem_is_still_priced_easy_with_one_warning(
    hmac_key: Path, caplog: pytest.LogCaptureFixture
):
    """An unresolved slug prices as Easy and warns once, writing no row."""
    resolve_difficulties(
        ["g1", "g2"], post=fake_post(DELETED), now=NOW, key_file=hmac_key
    )
    table = load_weights(key_file=hmac_key)

    with caplog.at_level(logging.WARNING):
        assert [table.weight("g1"), table.weight("g2")] == [1, 1]
        table.warn_unknown()

    assert caplog.text.count("no trusted difficulty row") == 1
    assert not _constants.DIFFICULTY_FILE.exists()


@pytest.mark.usefixtures("data_dir")
def test_a_transient_failure_is_retried_on_the_next_call(hmac_key: Path):
    """A transport error leaves no mark, so the next call retries."""
    post = fake_post(GraphQLResult(transport_error="boom"))
    for _ in range(2):
        resolve_difficulties(["x"], post=post, now=NOW, key_file=hmac_key)

    assert len(post.calls) == 2
    assert not _constants.DIFFICULTY_UNRESOLVED_FILE.exists()


@pytest.mark.usefixtures("data_dir")
def test_a_later_answer_clears_the_mark(hmac_key: Path):
    """A successful later lookup clears the unresolved mark."""
    resolve_difficulties(["back"], post=fake_post(DELETED), now=NOW, key_file=hmac_key)
    later = NOW + DAY

    resolve_difficulties(
        ["back"],
        post=fake_post(question_result("Medium")),
        now=later,
        key_file=hmac_key,
    )

    assert load_weights(key_file=hmac_key).weight("back") == 2
    assert load_unresolved(_constants.DIFFICULTY_UNRESOLVED_FILE) == {}


@pytest.mark.usefixtures("data_dir")
def test_the_pool_cache_answers_a_marked_slug_without_waiting(hmac_key: Path):
    """The pool cache resolves a marked slug at once and clears the mark."""
    resolve_difficulties(["a"], post=fake_post(DELETED), now=NOW, key_file=hmac_key)
    seed_pool({"a": "Hard"})
    post = fake_post()

    result = resolve_difficulties(["a"], post=post, now=NOW, key_file=hmac_key)

    assert (result.resolved, result.backed_off, len(post.calls)) == (1, 0, 0)
    assert load_unresolved(_constants.DIFFICULTY_UNRESOLVED_FILE) == {}


@pytest.mark.usefixtures("data_dir")
def test_the_harvester_path_backs_off_too(hmac_key: Path):
    """resolve_probe honours the same once-a-day backoff."""
    probe = probe_of("a")
    post = fake_post(DELETED)
    for minutes in range(3):
        resolve_probe(
            probe, post=post, now=NOW + timedelta(minutes=minutes), key_file=hmac_key
        )

    assert len(post.calls) == 1


def test_a_clock_set_back_does_not_back_off_forever():
    """A mark far in the future does not count as backed off."""
    marks = {"a": NOW.timestamp() + 10 * RETRY_SECONDS}

    assert not is_backed_off(marks, "a", now=NOW.timestamp())


@pytest.mark.usefixtures("data_dir")
def test_marks_round_trip_and_junk_reads_as_empty():
    """Marks round-trip; junk files and non-numeric values read as empty."""
    path = _constants.DIFFICULTY_UNRESOLVED_FILE
    assert load_unresolved(path) == {}
    assert save_unresolved(path, {"a": 5.0})
    assert load_unresolved(path) == {"a": 5.0}
    path.write_text("not json", encoding="utf-8")
    assert load_unresolved(path) == {}
    path.write_text("[1]", encoding="utf-8")
    assert load_unresolved(path) == {}
    path.write_text('{"a": "x", "b": true, "c": 7}', encoding="utf-8")
    assert load_unresolved(path) == {"c": 7.0}
    assert json.loads(save_and_read(path)) == {"z": 1.0}


def save_and_read(path: Path) -> str:
    """Save one mark to path and return the raw file text."""
    save_unresolved(path, {"z": 1.0})
    return path.read_text(encoding="utf-8")


def test_an_unwritable_mark_file_is_logged_not_raised(
    data_dir: Path, caplog: pytest.LogCaptureFixture
):
    """A mark file that cannot be written logs a warning instead of raising."""
    blocked = data_dir / "dir"
    blocked.mkdir()

    with caplog.at_level(logging.WARNING):
        assert not save_unresolved(blocked, {"a": 1.0})

    assert "could not write" in caplog.text
    assert _difficulty_negative.RETRY_SECONDS == 24 * 3600
