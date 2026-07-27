"""Tests for the on-disk pool mirror."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from leetcode_guard._pool_cache import CachedPool, read_cache, write_cache
from leetcode_guard._problem import parse_problem
from leetcode_guard.tests._net_fixtures import problem_row

if TYPE_CHECKING:
    from pathlib import Path


def make_pool(*, fetched_at: float = 1000.0, complete: bool = True) -> CachedPool:
    rows = [
        problem_row("two-sum", ac_rate=57.9, topics=["array"]),
        problem_row("add-two"),
    ]
    problems = tuple(p for p in (parse_problem(row) for row in rows) if p is not None)
    return CachedPool(problems=problems, fetched_at=fetched_at, complete=complete)


def test_round_trip_preserves_every_field(tmp_path: Path):
    path = tmp_path / "pool.json"
    original = make_pool()

    assert write_cache(path, original)
    loaded = read_cache(path)

    assert loaded is not None
    assert loaded.fetched_at == original.fetched_at
    assert loaded.complete == original.complete
    assert [p.title_slug for p in loaded.problems] == ["two-sum", "add-two"]
    assert loaded.problems[0].topics == ("array",)


def test_write_creates_the_parent_directory(tmp_path: Path):
    path = tmp_path / "nested" / "deeper" / "pool.json"

    assert write_cache(path, make_pool())
    assert path.exists()


def test_write_failure_is_reported_not_raised(tmp_path: Path):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")

    assert not write_cache(blocker / "pool.json", make_pool())


def test_missing_file_reads_as_none(tmp_path: Path):
    assert read_cache(tmp_path / "absent.json") is None


@pytest.mark.parametrize(
    "content",
    [
        "not json at all",
        '["not", "an", "object"]',
        '{"version": 99, "fetched_at": 1, "problems": []}',
        '{"version": 1, "problems": []}',
        '{"version": 1, "fetched_at": "soon", "problems": []}',
        '{"version": 1, "fetched_at": true, "problems": []}',
        '{"version": 1, "fetched_at": 1}',
        '{"version": 1, "fetched_at": 1, "problems": "none"}',
    ],
)
def test_every_corruption_mode_reads_as_none(tmp_path: Path, content: str):
    path = tmp_path / "pool.json"
    path.write_text(content, encoding="utf-8")

    assert read_cache(path) is None


def test_unreadable_file_reads_as_none(tmp_path: Path):
    path = tmp_path / "pool.json"
    path.mkdir()

    assert read_cache(path) is None


def test_malformed_problem_rows_are_skipped(tmp_path: Path):
    path = tmp_path / "pool.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "fetched_at": 5.0,
                "complete": True,
                "problems": [problem_row("kept"), {"nope": 1}],
            }
        ),
        encoding="utf-8",
    )

    loaded = read_cache(path)

    assert loaded is not None
    assert [p.title_slug for p in loaded.problems] == ["kept"]


def test_complete_defaults_to_false_when_absent(tmp_path: Path):
    path = tmp_path / "pool.json"
    path.write_text(
        json.dumps({"version": 1, "fetched_at": 5.0, "problems": []}), encoding="utf-8"
    )

    loaded = read_cache(path)

    assert loaded is not None
    assert not loaded.complete


def test_freshness_window():
    pool = make_pool(fetched_at=1000.0)

    assert pool.is_fresh(now=1000.0, ttl=100.0)
    assert pool.is_fresh(now=1099.0, ttl=100.0)
    assert not pool.is_fresh(now=1100.0, ttl=100.0)


def test_a_backwards_clock_reads_as_stale_not_as_infinitely_fresh():
    pool = make_pool(fetched_at=1000.0)

    assert pool.age_seconds(500.0) < 0
    assert not pool.is_fresh(now=500.0, ttl=100.0)
