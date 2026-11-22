"""The refresher treats an unsigned, edited or cut-short pool cache as stale.

A normal refresh (the arming run, ``--probe``) refetches and rewrites it signed,
so nobody has to do anything after the signing change is deployed. Display reads
the same cache unverified, unchanged.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from leetcode_guard._auth import AuthState
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._pool_cache import (
    INCOMPLETE_RETRY_SECONDS,
    CachedPool,
    read_cache,
    write_cache,
)
from leetcode_guard._pool_resolve import SolvedKnowledge, resolve_pool
from leetcode_guard.tests._net_fixtures import fake_post, pool_result, problem_row
from leetcode_guard.tests._theory_scenario import world
from leetcode_guard.tests.test_pool_signed import cache_path, edit_cache, mark_paid
from leetcode_guard.tests.test_problem import make

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest

SIGNED_OUT = AuthState(cookies=None, note="signed out")


def refetching(slugs: tuple[str, ...]) -> Callable[..., GraphQLResult]:
    """A post that serves a complete pool of ``slugs``."""
    rows = [problem_row(slug, difficulty="Easy") for slug in slugs]
    return fake_post(pool_result(rows, total=len(rows)))


def test_a_tampered_fresh_cache_is_refetched_and_rewritten_signed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hmac_key: Path
):
    """An edited cache is stale to the refresher, whatever its fetched_at says."""
    world(tmp_path, monkeypatch)
    edit_cache(mark_paid)
    solved = SolvedKnowledge(auth=SIGNED_OUT, key_file=hmac_key)
    before = read_cache(cache_path(), key_file=hmac_key)
    assert before is not None
    assert not before.verified

    resolution = resolve_pool(
        refetching(("fresh",)), cache_path(), now=1.0, solved=solved
    )

    assert resolution.source == "live"
    again = read_cache(cache_path(), key_file=hmac_key)
    assert again is not None
    assert (again.verified, again.complete) == (True, True)
    assert [p.title_slug for p in again.problems] == ["fresh"]


def test_a_signed_pool_round_trips_verified_only_under_its_own_key(
    tmp_path: Path, hmac_key: Path, missing_key: Path
):
    """What the guard writes reads back verified; another or no key says no."""
    path = tmp_path / "pool.json"
    pool = CachedPool((make("a1"),), fetched_at=5.0, complete=True)

    assert write_cache(path, pool, key_file=hmac_key)

    loaded = read_cache(path, key_file=hmac_key)
    assert loaded is not None
    assert loaded.verified
    other = read_cache(path, key_file=missing_key)
    assert other is not None
    assert not other.verified


def test_an_unreadable_key_writes_the_cache_unsigned_and_says_so(
    tmp_path: Path, missing_key: Path, caplog: pytest.LogCaptureFixture
):
    """The cache is an optimisation: no key costs the signature, not the file."""
    path = tmp_path / "pool.json"

    with caplog.at_level(logging.WARNING):
        assert write_cache(
            path, CachedPool((make("a1"),), 5.0, True), key_file=missing_key
        )

    loaded = read_cache(path, key_file=missing_key)
    assert loaded is not None
    assert not loaded.verified
    assert "written unsigned" in caplog.text


def test_an_incomplete_pool_is_retried_after_an_hour_not_a_week(
    tmp_path: Path, hmac_key: Path
):
    """A cut-short fetch must not hold the phase for the whole TTL."""
    path = tmp_path / "pool.json"
    solved = SolvedKnowledge(auth=SIGNED_OUT, key_file=hmac_key)
    partial = CachedPool((make("a1"),), fetched_at=0.0, complete=False)
    write_cache(path, partial, key_file=hmac_key)
    wait = INCOMPLETE_RETRY_SECONDS

    soon = resolve_pool(refetching(("full",)), path, now=wait - 1, solved=solved)
    later = resolve_pool(refetching(("full",)), path, now=wait + 1, solved=solved)

    assert (soon.source, later.source) == ("cache", "live")
    assert [p.title_slug for p in read_pool(path, hmac_key).problems] == ["full"]


def read_pool(path: Path, key: Path) -> CachedPool:
    """The pool at ``path``, which must be readable."""
    pool = read_cache(path, key_file=key)
    assert pool is not None
    return pool


def test_a_signed_complete_cache_is_not_refetched(tmp_path: Path, hmac_key: Path):
    """The refresher still spares the 41-page fetch for a good cache."""
    path = tmp_path / "pool.json"
    good = CachedPool((make("a1"),), fetched_at=0.0, complete=True)
    write_cache(path, good, key_file=hmac_key)
    solved = SolvedKnowledge(auth=SIGNED_OUT, key_file=hmac_key)

    resolution = resolve_pool(refetching(("other",)), path, now=1.0, solved=solved)

    assert resolution.source == "cache"


def test_an_unsigned_cache_with_no_network_is_still_listed_as_stale(
    tmp_path: Path, hmac_key: Path
):
    """Refetch failing falls back to the cache for display, with the usual note."""
    path = tmp_path / "pool.json"
    write_cache(path, CachedPool((make("a1"),), 0.0, True), key_file=hmac_key)
    raw = json.loads(path.read_text(encoding="utf-8"))
    del raw["hmac"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    down = fake_post(GraphQLResult(transport_error="down"))

    resolution = resolve_pool(
        down, path, now=1.0, solved=SolvedKnowledge(auth=SIGNED_OUT, key_file=hmac_key)
    )

    assert resolution.source == "stale-cache"
    assert [p.title_slug for p in resolution.problems] == ["a1"]
