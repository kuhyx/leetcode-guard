"""A cut-short refresh never replaces a verified, complete pool cache.

One failed page of ~41 at the weekly refresh used to overwrite a good cache with
a partial one, and the theory phase (verified AND complete only) then could not
decide until a later refetch worked. Every other case is unchanged: no cache,
an unverified cache or an already incomplete cache is still replaced.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from leetcode_guard import _constants
from leetcode_guard._auth import AuthState
from leetcode_guard._ledger_io import Ledger
from leetcode_guard._phase_inputs import gather_phase
from leetcode_guard._pool_cache import CachedPool, read_cache, write_cache
from leetcode_guard._pool_resolve import SolvedKnowledge, resolve_pool
from leetcode_guard.tests._net_fixtures import (
    FakePost,
    fake_post,
    pool_result,
    problem_row,
)
from leetcode_guard.tests._theory_scenario import world
from leetcode_guard.tests.test_pool_signed import (
    cache_path,
    drop_signature,
    solve_a_then_teach_b,
)
from leetcode_guard.tests.test_problem import make

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

SIGNED_OUT = AuthState(cookies=None, note="signed out")
STALE = _constants.POOL_TTL_SECONDS + 1.0
"""A ``now`` that makes a cache written at 0.0 stale by TTL."""


def partial_post() -> FakePost:
    """A post whose pool stops one problem into a 999-problem set."""
    return fake_post(pool_result([problem_row("partial")], total=999))


def full_post() -> FakePost:
    """A post that serves a complete pool of one problem."""
    return fake_post(pool_result([problem_row("whole")], total=1))


def write_good(path: Path, key: Path) -> None:
    """A verified, complete pool written at 0.0."""
    pool = CachedPool((make("a1", topics=["x"]),), fetched_at=0.0, complete=True)
    write_cache(path, pool, key_file=key)


def test_an_incomplete_fetch_keeps_a_good_cache_byte_identical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    hmac_key: Path,
    caplog: pytest.LogCaptureFixture,
):
    """The file is untouched, still verified and complete, and the phase decides."""
    world(tmp_path, monkeypatch)
    solve_a_then_teach_b(hmac_key)
    write_good(cache_path(), hmac_key)
    before = cache_path().read_bytes()
    solved = SolvedKnowledge(auth=SIGNED_OUT, key_file=hmac_key)

    with caplog.at_level(logging.WARNING):
        resolution = resolve_pool(
            partial_post(), cache_path(), now=STALE, solved=solved
        )

    assert cache_path().read_bytes() == before
    kept = read_cache(cache_path(), key_file=hmac_key)
    assert kept is not None
    assert (kept.verified, kept.complete) == (True, True)
    assert gather_phase(Ledger(), key_file=hmac_key) is not None
    assert resolution.source == "stale-cache"
    assert [p.title_slug for p in resolution.problems] == ["a1"]
    assert any("refresh was incomplete" in note for note in resolution.notes)
    assert "kept the last complete problem list" in caplog.text


def test_the_kept_cache_stays_stale_so_the_next_run_refetches(
    tmp_path: Path, hmac_key: Path
):
    """Nothing is stamped: the next refresher run tries again and may replace it."""
    path = tmp_path / "pool.json"
    write_good(path, hmac_key)
    solved = SolvedKnowledge(auth=SIGNED_OUT, key_file=hmac_key)

    first = resolve_pool(partial_post(), path, now=STALE, solved=solved)
    second = resolve_pool(full_post(), path, now=STALE + 1, solved=solved)

    assert (first.source, second.source) == ("stale-cache", "live")
    replaced = read_cache(path, key_file=hmac_key)
    assert replaced is not None
    assert [p.title_slug for p in replaced.problems] == ["whole"]
    assert (replaced.verified, replaced.complete) == (True, True)


def test_a_complete_fetch_replaces_a_good_stale_cache(tmp_path: Path, hmac_key: Path):
    """The weekly refresh still works when every page comes back."""
    path = tmp_path / "pool.json"
    write_good(path, hmac_key)
    solved = SolvedKnowledge(auth=SIGNED_OUT, key_file=hmac_key)

    resolution = resolve_pool(full_post(), path, now=STALE, solved=solved)

    assert resolution.source == "live"
    fresh = read_cache(path, key_file=hmac_key)
    assert fresh is not None
    assert [p.title_slug for p in fresh.problems] == ["whole"]


def unsign(path: Path) -> None:
    """Strip the signature, as every cache written before signing looks."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    drop_signature(raw)
    path.write_text(json.dumps(raw), encoding="utf-8")


def test_an_incomplete_fetch_still_replaces_every_other_kind_of_cache(
    tmp_path: Path, hmac_key: Path
):
    """No cache, an unsigned one and an incomplete one all take the partial pool."""
    solved = SolvedKnowledge(auth=SIGNED_OUT, key_file=hmac_key)
    missing = tmp_path / "missing.json"
    unsigned = tmp_path / "unsigned.json"
    write_good(unsigned, hmac_key)
    unsign(unsigned)
    cut = tmp_path / "cut.json"
    write_cache(
        cut,
        CachedPool((make("a1"),), fetched_at=0.0, complete=False),
        key_file=hmac_key,
    )

    for path in (missing, unsigned, cut):
        resolution = resolve_pool(partial_post(), path, now=STALE, solved=solved)
        stored = read_cache(path, key_file=hmac_key)

        assert resolution.source == "live"
        assert stored is not None
        assert {p.title_slug for p in stored.problems} == {"partial"}
        assert (stored.verified, stored.complete) == (True, False)
