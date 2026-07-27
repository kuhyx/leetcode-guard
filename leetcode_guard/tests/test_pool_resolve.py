"""Tests for the live/cache/stale-cache/nothing ladder."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._auth import AuthState, Cookies
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._pool_cache import CachedPool, read_cache, write_cache
from leetcode_guard._pool_resolve import resolve_pool
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

    resolution = resolve_pool(post, path, now=150.0, auth=SIGNED_OUT, ttl=1000.0)

    assert resolution.source == "cache"
    assert [p.title_slug for p in resolution.problems] == ["from-cache"]
    assert post.calls == []


def test_a_stale_cache_triggers_a_live_fetch_and_is_replaced(tmp_path: Path):
    path = tmp_path / "pool.json"
    write_cache(path, cached("old", fetched_at=0.0))
    post = fake_post(pool_result([problem_row("fresh")], total=1))

    resolution = resolve_pool(post, path, now=10_000.0, auth=SIGNED_OUT, ttl=100.0)

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

    resolution = resolve_pool(post, path, now=3 * day, auth=SIGNED_OUT, ttl=day)

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
        auth=SIGNED_OUT,
        ttl=day,
    )

    assert any("1 day ago" in note for note in resolution.notes)


def test_no_cache_and_no_network_still_returns_a_usable_resolution(tmp_path: Path):
    resolution = resolve_pool(
        fake_post(GraphQLResult(transport_error="down")),
        tmp_path / "absent.json",
        now=0.0,
        auth=SIGNED_OUT,
    )

    assert resolution.source == "none"
    assert resolution.empty
    assert any("Any accepted submission counts" in note for note in resolution.notes)


def test_post_none_forces_cache_only_resolution(tmp_path: Path):
    """``--status`` and the MCP server must never trigger a live fetch."""
    resolution = resolve_pool(None, tmp_path / "absent.json", now=0.0, auth=SIGNED_OUT)

    assert resolution.source == "none"


def test_incomplete_fetch_is_announced(tmp_path: Path):
    post = fake_post(pool_result([problem_row("partial")], total=999))

    resolution = resolve_pool(post, tmp_path / "pool.json", now=0.0, auth=SIGNED_OUT)

    assert resolution.source == "live"
    assert any("may be incomplete" in note for note in resolution.notes)


def test_the_auth_note_is_always_included(tmp_path: Path):
    resolution = resolve_pool(
        fake_post(pool_result([problem_row("x")], total=1)),
        tmp_path / "pool.json",
        now=0.0,
        auth=SIGNED_OUT,
    )

    assert resolution.notes[0] == "signed out note"


def test_signed_in_hides_solved_problems(tmp_path: Path):
    post = fake_post(
        pool_result(
            [problem_row("done", status="ac"), problem_row("todo", status="notac")],
            total=2,
        )
    )

    resolution = resolve_pool(post, tmp_path / "pool.json", now=0.0, auth=SIGNED_IN)

    assert [p.title_slug for p in resolution.problems] == ["todo"]


def test_a_pool_of_only_premium_problems_reports_no_suggestions(tmp_path: Path):
    post = fake_post(pool_result([problem_row("premium", paid_only=True)], total=1))

    resolution = resolve_pool(post, tmp_path / "pool.json", now=0.0, auth=SIGNED_OUT)

    assert resolution.empty
    assert resolution.source == "live"
    assert any("Any accepted submission counts" in note for note in resolution.notes)
