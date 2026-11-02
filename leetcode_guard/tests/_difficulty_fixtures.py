"""Shared builders for the difficulty tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard import _constants
from leetcode_guard._difficulty import difficulty_row
from leetcode_guard._ledger_io import Ledger, append, save_ledger
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._pool_cache import CachedPool, write_cache
from leetcode_guard._problem import parse_problem
from leetcode_guard.tests._ledger_fixtures import NOW
from leetcode_guard.tests._net_fixtures import problem_row

if TYPE_CHECKING:
    from pathlib import Path


def question_result(difficulty: str) -> GraphQLResult:
    return GraphQLResult(data={"question": {"difficulty": difficulty}})


def write_rows(path: Path, key: Path, rows: dict[str, str]) -> None:
    ledger = Ledger()
    append(
        ledger,
        [
            difficulty_row(slug, level, now=NOW, key_file=key)
            for slug, level in rows.items()
        ],
    )
    save_ledger(path, ledger)


def seed_pool(rows: dict[str, str]) -> None:
    problems = tuple(
        parsed
        for slug, level in rows.items()
        if (parsed := parse_problem(problem_row(slug, difficulty=level)))
    )
    write_cache(
        _constants.POOL_CACHE_FILE,
        CachedPool(problems=problems, fetched_at=1.0, complete=True),
    )
