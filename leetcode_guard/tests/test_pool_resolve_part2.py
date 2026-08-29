"""Continued from :mod:`leetcode_guard.tests.test_pool_resolve`, split for the 250-line cap."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._pool_cache import write_cache
from leetcode_guard._pool_resolve import SolvedKnowledge, resolve_pool
from leetcode_guard.tests._net_fixtures import (
    fake_post,
    pool_result,
    problem_row,
    status_result,
)

if TYPE_CHECKING:
    from pathlib import Path

from leetcode_guard.tests.test_pool_resolve import (
    SIGNED_IN,
    SIGNED_OUT,
    cached,
    path_of,
)


def test_a_live_check_drops_a_solve_the_stored_data_missed(tmp_path: Path):
    """The stored pool is written at most once a week. A problem solved since
    then still looks unsolved in it, which is how a solve from two days ago
    reached the top of the list."""
    write_cache(path_of(tmp_path), cached("solved-today", "still-open"))
    post = fake_post(
        status_result("solved-today", "ac"), status_result("still-open", "notac")
    )

    resolution = resolve_pool(
        post,
        path_of(tmp_path),
        now=0.0,
        solved=SolvedKnowledge(auth=SIGNED_IN),
        ttl=1_000.0,
    )

    assert [p.title_slug for p in resolution.problems] == ["still-open"]
    assert any("Checked with LeetCode just now" in n for n in resolution.notes)


def test_a_dropped_problem_is_backfilled_from_further_down(tmp_path: Path):
    """Dropping without backfilling would shrink the list every time a solve
    landed, so the surface would slowly empty out."""
    write_cache(path_of(tmp_path), cached("a", "b", "c"))
    post = fake_post(
        status_result("a", "ac"),
        status_result("b", "notac"),
        status_result("c", "notac"),
    )

    resolution = resolve_pool(
        post,
        path_of(tmp_path),
        now=0.0,
        solved=SolvedKnowledge(auth=SIGNED_IN, verify_limit=2),
        ttl=1_000.0,
    )

    assert [p.title_slug for p in resolution.problems] == ["b", "c"]


def test_an_unreachable_endpoint_stops_the_sweep_instead_of_paying_for_it(
    tmp_path: Path,
):
    """Nothing answered, so the remaining requests would be equally blind.
    Sending them anyway is how a rate-limit gets provoked."""
    write_cache(path_of(tmp_path), cached("a", "b", "c"))
    post = fake_post(GraphQLResult(transport_error="down"))

    resolution = resolve_pool(
        post,
        path_of(tmp_path),
        now=0.0,
        solved=SolvedKnowledge(auth=SIGNED_IN, verify_limit=2),
        ttl=1_000.0,
    )

    assert [p.title_slug for p in resolution.problems] == ["a", "b", "c"]
    assert len(post.calls) == 2
    assert any("Could not reach LeetCode" in n for n in resolution.notes)


def test_never_attempted_problems_do_not_look_like_a_dead_session(tmp_path: Path):
    """A signed-in user's unopened problems all return null.

    Treating that as an outage made the lock claim it could not check while
    holding a verified cookie -- and abandon the rest of the sweep, so a solved
    problem further down would have survived.
    """
    write_cache(path_of(tmp_path), cached("a", "b"))
    post = fake_post(status_result("a", None))

    resolution = resolve_pool(
        post,
        path_of(tmp_path),
        now=0.0,
        solved=SolvedKnowledge(auth=SIGNED_IN),
        ttl=1_000.0,
    )

    assert [p.title_slug for p in resolution.problems] == ["a", "b"]
    assert any("none of these are solved yet" in n for n in resolution.notes)
    assert not any("Could not reach" in n for n in resolution.notes)


def test_the_live_check_only_pays_for_what_is_displayed(tmp_path: Path):
    """4019 problems must not mean 4019 requests on the pre-window path."""
    write_cache(path_of(tmp_path), cached(*[f"p{i}" for i in range(50)]))
    post = fake_post(status_result("p0", "notac"))

    resolve_pool(
        post,
        path_of(tmp_path),
        now=0.0,
        solved=SolvedKnowledge(auth=SIGNED_IN, verify_limit=3),
        ttl=1_000.0,
    )

    assert len(post.calls) == 3


def test_status_never_triggers_a_live_check(tmp_path: Path):
    """`post=None` is the read-only contract `--status` and MCP rely on."""
    write_cache(path_of(tmp_path), cached("a"))

    resolution = resolve_pool(
        None,
        path_of(tmp_path),
        now=0.0,
        solved=SolvedKnowledge(auth=SIGNED_IN),
        ttl=1_000.0,
    )

    assert [p.title_slug for p in resolution.problems] == ["a"]
    assert not any("Checked with LeetCode" in n for n in resolution.notes)


def test_a_clean_live_check_says_so(tmp_path: Path):
    write_cache(path_of(tmp_path), cached("a"))
    post = fake_post(status_result("a", "notac"))

    resolution = resolve_pool(
        post,
        path_of(tmp_path),
        now=0.0,
        solved=SolvedKnowledge(auth=SIGNED_IN),
        ttl=1_000.0,
    )

    assert any("none of these are solved yet" in n for n in resolution.notes)


def test_signed_in_hides_solved_problems(tmp_path: Path):
    post = fake_post(
        pool_result(
            [problem_row("done", status="ac"), problem_row("todo", status="notac")],
            total=2,
        )
    )

    resolution = resolve_pool(
        post, tmp_path / "pool.json", now=0.0, solved=SolvedKnowledge(auth=SIGNED_IN)
    )

    assert [p.title_slug for p in resolution.problems] == ["todo"]


def test_a_pool_of_only_premium_problems_reports_no_suggestions(tmp_path: Path):
    post = fake_post(pool_result([problem_row("premium", paid_only=True)], total=1))

    resolution = resolve_pool(
        post, tmp_path / "pool.json", now=0.0, solved=SolvedKnowledge(auth=SIGNED_OUT)
    )

    assert resolution.empty
    assert resolution.source == "live"
    assert any("Any accepted submission counts" in note for note in resolution.notes)
