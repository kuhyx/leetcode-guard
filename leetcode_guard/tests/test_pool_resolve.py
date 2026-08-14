"""Tests for the live/cache/stale-cache/nothing ladder."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._auth import AuthState, Cookies
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._pool_cache import CachedPool, read_cache, write_cache
from leetcode_guard._pool_resolve import SolvedKnowledge, resolve_pool
from leetcode_guard._problem import parse_problem
from leetcode_guard.tests._net_fixtures import fake_post, pool_result, problem_row

if TYPE_CHECKING:
    from pathlib import Path

SIGNED_OUT = AuthState(cookies=None, note="signed out note")
SIGNED_IN = AuthState(cookies=Cookies(session="s", csrf="c"), note="signed in note")


def cached(*slugs: str, fetched_at: float = 0.0) -> CachedPool:
    problems = tuple(
        p for p in (parse_problem(problem_row(slug)) for slug in slugs) if p is not None
    )
    return CachedPool(problems=problems, fetched_at=fetched_at, complete=True)


def test_a_fresh_cache_wins_and_makes_no_request(tmp_path: Path):
    path = tmp_path / "pool.json"
    write_cache(path, cached("from-cache", fetched_at=100.0))
    post = fake_post(pool_result([problem_row("from-network")]))

    resolution = resolve_pool(
        post, path, now=150.0, solved=SolvedKnowledge(auth=SIGNED_OUT), ttl=1000.0
    )

    assert resolution.source == "cache"
    assert [p.title_slug for p in resolution.problems] == ["from-cache"]
    assert post.calls == []


def test_a_stale_cache_triggers_a_live_fetch_and_is_replaced(tmp_path: Path):
    path = tmp_path / "pool.json"
    write_cache(path, cached("old", fetched_at=0.0))
    post = fake_post(pool_result([problem_row("fresh")], total=1))

    resolution = resolve_pool(
        post, path, now=10_000.0, solved=SolvedKnowledge(auth=SIGNED_OUT), ttl=100.0
    )

    assert resolution.source == "live"
    assert [p.title_slug for p in resolution.problems] == ["fresh"]
    reloaded = read_cache(path)
    assert reloaded is not None
    assert reloaded.fetched_at == 10_000.0


def test_a_failed_fetch_falls_back_to_the_stale_cache_and_says_so(tmp_path: Path):
    path = tmp_path / "pool.json"
    day = 86_400.0
    write_cache(path, cached("old", fetched_at=0.0))
    post = fake_post(GraphQLResult(transport_error="down"))

    resolution = resolve_pool(
        post, path, now=3 * day, solved=SolvedKnowledge(auth=SIGNED_OUT), ttl=day
    )

    assert resolution.source == "stale-cache"
    assert [p.title_slug for p in resolution.problems] == ["old"]
    assert any("3 days ago" in note for note in resolution.notes)
    assert any("Could not refresh" in note for note in resolution.notes)


def test_one_day_stale_note_is_singular(tmp_path: Path):
    path = tmp_path / "pool.json"
    day = 86_400.0
    write_cache(path, cached("old", fetched_at=0.0))

    resolution = resolve_pool(
        fake_post(GraphQLResult(transport_error="down")),
        path,
        now=1.5 * day,
        solved=SolvedKnowledge(auth=SIGNED_OUT),
        ttl=day,
    )

    assert any("1 day ago" in note for note in resolution.notes)


def test_no_cache_and_no_network_still_returns_a_usable_resolution(tmp_path: Path):
    resolution = resolve_pool(
        fake_post(GraphQLResult(transport_error="down")),
        tmp_path / "absent.json",
        now=0.0,
        solved=SolvedKnowledge(auth=SIGNED_OUT),
    )

    assert resolution.source == "none"
    assert resolution.empty
    assert any("Any accepted submission counts" in note for note in resolution.notes)


def test_post_none_forces_cache_only_resolution(tmp_path: Path):
    """``--status`` and the MCP server must never trigger a live fetch."""
    resolution = resolve_pool(
        None, tmp_path / "absent.json", now=0.0, solved=SolvedKnowledge(auth=SIGNED_OUT)
    )

    assert resolution.source == "none"


def test_incomplete_fetch_is_announced(tmp_path: Path):
    post = fake_post(pool_result([problem_row("partial")], total=999))

    resolution = resolve_pool(
        post, tmp_path / "pool.json", now=0.0, solved=SolvedKnowledge(auth=SIGNED_OUT)
    )

    assert resolution.source == "live"
    assert any("may be incomplete" in note for note in resolution.notes)


def test_the_auth_note_is_always_included(tmp_path: Path):
    resolution = resolve_pool(
        fake_post(pool_result([problem_row("x")], total=1)),
        tmp_path / "pool.json",
        now=0.0,
        solved=SolvedKnowledge(auth=SIGNED_OUT),
    )

    assert resolution.notes[0] == "signed out note"


def test_the_ledger_hides_a_solve_that_an_expired_session_cannot_report(
    tmp_path: Path,
):
    """The regression test for the bug this filter was built for.

    On 2026-08-14 the surface offered `digit-frequency-score` as suggestion #1
    two days after it had been solved, under a note claiming solved problems
    were hidden. The session had expired on 2026-08-09, and because the pool
    query is public, LeetCode answered with a complete, healthy-looking list
    whose every `status` was null -- so the filter had nothing to match on.
    """
    post = fake_post(
        pool_result(
            [problem_row("digit-frequency-score"), problem_row("never-seen")],
            total=2,
        )
    )

    resolution = resolve_pool(
        post,
        tmp_path / "pool.json",
        now=0.0,
        solved=SolvedKnowledge(
            auth=SIGNED_IN, slugs=frozenset({"digit-frequency-score"})
        ),
    )

    assert [p.title_slug for p in resolution.problems] == ["never-seen"]
    assert any("already solved on this device" in n for n in resolution.notes)


def test_the_ledger_note_does_not_claim_to_know_every_solve(tmp_path: Path):
    """The recent-AC feed is capped at 20 rows, so the ledger is a lower bound.

    Overstating it would be the same defect as the note it replaced.
    """
    post = fake_post(pool_result([problem_row("x")], total=1))

    resolution = resolve_pool(
        post,
        tmp_path / "pool.json",
        now=0.0,
        solved=SolvedKnowledge(auth=SIGNED_OUT, slugs=frozenset({"a", "b"})),
    )

    assert any("at least 2 problems" in n for n in resolution.notes)


def test_no_ledger_slugs_adds_no_note(tmp_path: Path):
    resolution = resolve_pool(
        fake_post(pool_result([problem_row("x")], total=1)),
        tmp_path / "pool.json",
        now=0.0,
        solved=SolvedKnowledge(auth=SIGNED_OUT),
    )

    assert not any("already solved on this device" in n for n in resolution.notes)


def test_a_solved_status_is_dropped_even_with_no_cookies(tmp_path: Path):
    """Dropping `exclude_solved` must not lose the statuses a partly
    authenticated fetch did manage to return -- the real cache had 10 of them
    among 4007 nulls, and gating on `auth.present` would have discarded all 10.
    """
    post = fake_post(
        pool_result(
            [problem_row("done", status="ac"), problem_row("todo", status="notac")],
            total=2,
        )
    )

    resolution = resolve_pool(
        post, tmp_path / "pool.json", now=0.0, solved=SolvedKnowledge(auth=SIGNED_OUT)
    )

    assert [p.title_slug for p in resolution.problems] == ["todo"]


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
