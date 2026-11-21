"""Resolve a hand-built pool with no network, the way status and MCP do."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._pool_cache import CachedPool, write_cache
from leetcode_guard._pool_resolve import SolvedKnowledge, resolve_pool
from leetcode_guard.tests.test_pool_resolve import SIGNED_OUT, path_of

if TYPE_CHECKING:
    from pathlib import Path

    from leetcode_guard._pool_resolve import PoolResolution
    from leetcode_guard._problem import Problem


def resolve_offline(tmp_path: Path, *problems: Problem) -> PoolResolution:
    """Cache ``problems`` and resolve them cache-only, signed out."""
    pool = CachedPool(problems=problems, fetched_at=0.0, complete=True)
    write_cache(path_of(tmp_path), pool)
    return resolve_pool(
        None,
        path_of(tmp_path),
        now=0.0,
        solved=SolvedKnowledge(auth=SIGNED_OUT),
        ttl=1_000.0,
    )
