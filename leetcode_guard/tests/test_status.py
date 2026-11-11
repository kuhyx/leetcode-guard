"""Tests for the read-only status view."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._ledger_io import save_ledger
from leetcode_guard._pool_cache import CachedPool, write_cache
from leetcode_guard._problem import parse_problem
from leetcode_guard._status import (
    PoolFiles,
    gather_status,
)
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    add_charge,
    ledger_with_credits,
)
from leetcode_guard.tests._net_fixtures import problem_row
from leetcode_guard.tests._status_fixtures import MONDAY_NOON, status_at

if TYPE_CHECKING:
    from pathlib import Path


def seed_pool(path: Path, *slugs: str) -> None:
    """Write a complete pool cache holding the given slugs."""
    problems = tuple(
        p for p in (parse_problem(problem_row(slug)) for slug in slugs) if p is not None
    )
    write_cache(
        path,
        CachedPool(
            problems=problems, fetched_at=MONDAY_NOON.timestamp(), complete=True
        ),
    )


def test_reports_a_locked_day(tmp_path: Path, hmac_key: Path):
    """With an empty ledger Monday reports locked, needing one solve."""
    snapshot = status_at(tmp_path, hmac_key)

    assert snapshot.verdict.locked
    assert snapshot.day == "2026-08-10"
    assert snapshot.weekday == "Monday"
    assert snapshot.cost == 1
    assert snapshot.verdict.needed == 1
    assert snapshot.verdict.state == "locked"


def test_reports_an_already_settled_day(tmp_path: Path, hmac_key: Path):
    """A charged day reports unlocked with the balance net of the charge."""
    path = tmp_path / "ledger.json"
    ledger = ledger_with_credits(2, day=MONDAY, key_file=hmac_key)
    add_charge(ledger, MONDAY, key_file=hmac_key)
    save_ledger(path, ledger)

    snapshot = status_at(tmp_path, hmac_key, ledger_path=path)

    assert not snapshot.verdict.locked
    assert snapshot.verdict.charged_today
    assert snapshot.balance.credits == 2
    assert snapshot.balance.charged == 1
    assert snapshot.balance.available == 1


def test_never_fetches_even_with_no_cache(tmp_path: Path, hmac_key: Path):
    """The network is blocked suite-wide, so reaching for it would raise. That
    this passes is the proof that status is genuinely offline."""
    snapshot = gather_status(
        now=MONDAY_NOON,
        ledger_path=tmp_path / "ledger.json",
        pool_files=PoolFiles(
            cache=tmp_path / "absent.json", cookies=tmp_path / "cookies.json"
        ),
        key_file=hmac_key,
    )

    assert snapshot.pool.source == "none"
    assert snapshot.pool.suggestions == ()


def test_suggestions_come_from_the_cache(tmp_path: Path, hmac_key: Path):
    """Suggestions are read from the pool cache as problem URLs."""
    cache = tmp_path / "pool.json"
    seed_pool(cache, "two-sum", "add-two")

    snapshot = gather_status(
        now=MONDAY_NOON,
        ledger_path=tmp_path / "ledger.json",
        pool_files=PoolFiles(cache=cache, cookies=tmp_path / "cookies.json"),
        key_file=hmac_key,
    )

    assert snapshot.pool.source == "cache"
    assert len(snapshot.pool.suggestions) == 2
    assert snapshot.pool.suggestions[0].url.startswith("https://leetcode.com/problems/")


def test_the_suggestion_limit_is_honoured(tmp_path: Path, hmac_key: Path):
    """The limit caps how many suggestions are returned."""
    cache = tmp_path / "pool.json"
    seed_pool(cache, "a", "b", "c", "d")

    snapshot = gather_status(
        now=MONDAY_NOON,
        ledger_path=tmp_path / "ledger.json",
        pool_files=PoolFiles(cache=cache, cookies=tmp_path / "cookies.json"),
        key_file=hmac_key,
        limit=2,
    )

    assert len(snapshot.pool.suggestions) == 2
