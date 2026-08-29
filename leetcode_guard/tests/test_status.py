"""Tests for the read-only status view."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING

from leetcode_guard import _status
from leetcode_guard._ledger import LedgerEntry
from leetcode_guard._ledger_io import Ledger, append, save_ledger
from leetcode_guard._pool_cache import CachedPool, write_cache
from leetcode_guard._problem import parse_problem
from leetcode_guard._status import (
    format_status,
    gather_status,
    snapshot_dict,
)
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    add_charge,
    forged_credit,
    ledger_with_credits,
)
from leetcode_guard.tests._net_fixtures import problem_row

if TYPE_CHECKING:
    from pathlib import Path

MONDAY_NOON = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


def seed_pool(path: Path, *slugs: str) -> None:
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
    snapshot = gather_status(
        now=MONDAY_NOON,
        ledger_path=tmp_path / "ledger.json",
        cache_path=tmp_path / "pool.json",
        cookies_path=tmp_path / "cookies.json",
        key_file=hmac_key,
    )

    assert snapshot.locked
    assert snapshot.day == "2026-08-10"
    assert snapshot.weekday == "Monday"
    assert snapshot.cost == 1
    assert snapshot.needed == 1
    assert snapshot.state == "locked"


def test_reports_an_already_settled_day(tmp_path: Path, hmac_key: Path):
    path = tmp_path / "ledger.json"
    ledger = ledger_with_credits(2, day=MONDAY, key_file=hmac_key)
    add_charge(ledger, MONDAY, key_file=hmac_key)
    save_ledger(path, ledger)

    snapshot = gather_status(
        now=MONDAY_NOON,
        ledger_path=path,
        cache_path=tmp_path / "pool.json",
        cookies_path=tmp_path / "cookies.json",
        key_file=hmac_key,
    )

    assert not snapshot.locked
    assert snapshot.charged_today
    assert snapshot.credits == 2
    assert snapshot.charged == 1
    assert snapshot.available == 1


def test_never_fetches_even_with_no_cache(tmp_path: Path, hmac_key: Path):
    """The network is blocked suite-wide, so reaching for it would raise. That
    this passes is the proof that status is genuinely offline."""
    snapshot = gather_status(
        now=MONDAY_NOON,
        ledger_path=tmp_path / "ledger.json",
        cache_path=tmp_path / "absent.json",
        cookies_path=tmp_path / "cookies.json",
        key_file=hmac_key,
    )

    assert snapshot.pool_source == "none"
    assert snapshot.suggestions == ()


def test_suggestions_come_from_the_cache(tmp_path: Path, hmac_key: Path):
    cache = tmp_path / "pool.json"
    seed_pool(cache, "two-sum", "add-two")

    snapshot = gather_status(
        now=MONDAY_NOON,
        ledger_path=tmp_path / "ledger.json",
        cache_path=cache,
        cookies_path=tmp_path / "cookies.json",
        key_file=hmac_key,
    )

    assert snapshot.pool_source == "cache"
    assert len(snapshot.suggestions) == 2
    assert snapshot.suggestions[0].url.startswith("https://leetcode.com/problems/")


def test_the_suggestion_limit_is_honoured(tmp_path: Path, hmac_key: Path):
    cache = tmp_path / "pool.json"
    seed_pool(cache, "a", "b", "c", "d")

    snapshot = gather_status(
        now=MONDAY_NOON,
        ledger_path=tmp_path / "ledger.json",
        cache_path=cache,
        cookies_path=tmp_path / "cookies.json",
        key_file=hmac_key,
        limit=2,
    )

    assert len(snapshot.suggestions) == 2


def test_integrity_problems_are_surfaced(tmp_path: Path, hmac_key: Path):
    path = tmp_path / "ledger.json"
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    append(ledger, [forged_credit()])
    append(ledger, [LedgerEntry("bad", "credit", "2026-08-10", "", 1)])
    save_ledger(path, ledger)

    snapshot = gather_status(
        now=MONDAY_NOON,
        ledger_path=path,
        cache_path=tmp_path / "pool.json",
        cookies_path=tmp_path / "cookies.json",
        key_file=hmac_key,
    )

    assert snapshot.tampered == 2
    assert snapshot.discounted == 2
    assert "tampered" in format_status(snapshot)
    assert "refused" in format_status(snapshot)


def test_an_untrusted_clock_is_surfaced(tmp_path: Path, hmac_key: Path):
    path = tmp_path / "ledger.json"
    ledger = Ledger()
    add_charge(ledger, MONDAY.replace(day=12), key_file=hmac_key)
    save_ledger(path, ledger)

    snapshot = gather_status(
        now=MONDAY_NOON,
        ledger_path=path,
        cache_path=tmp_path / "pool.json",
        cookies_path=tmp_path / "cookies.json",
        key_file=hmac_key,
    )

    assert not snapshot.clock_trusted
    assert "UNTRUSTED" in format_status(snapshot)


def test_an_unreadable_key_is_surfaced(tmp_path: Path, missing_key: Path):
    snapshot = gather_status(
        now=MONDAY_NOON,
        ledger_path=tmp_path / "ledger.json",
        cache_path=tmp_path / "pool.json",
        cookies_path=tmp_path / "cookies.json",
        key_file=missing_key,
    )

    assert not snapshot.integrity_ok
    assert "integrity  OFF" in format_status(snapshot)


def test_unparsable_rows_are_surfaced(tmp_path: Path, hmac_key: Path):
    path = tmp_path / "ledger.json"
    path.write_text('{"version": 1, "entries": [{"junk": 1}]}', encoding="utf-8")

    snapshot = gather_status(
        now=MONDAY_NOON,
        ledger_path=path,
        cache_path=tmp_path / "pool.json",
        cookies_path=tmp_path / "cookies.json",
        key_file=hmac_key,
    )

    assert snapshot.unparsable == 1
    assert "unreadable" in format_status(snapshot)


def test_the_shortfall_line_is_singular_for_one(tmp_path: Path, hmac_key: Path):
    snapshot = gather_status(
        now=MONDAY_NOON,
        ledger_path=tmp_path / "ledger.json",
        cache_path=tmp_path / "pool.json",
        cookies_path=tmp_path / "cookies.json",
        key_file=hmac_key,
    )

    assert "1 more solve to unlock" in format_status(snapshot)


def test_snapshot_dict_is_plain_data(tmp_path: Path, hmac_key: Path):
    snapshot = gather_status(
        now=MONDAY_NOON,
        ledger_path=tmp_path / "ledger.json",
        cache_path=tmp_path / "pool.json",
        cookies_path=tmp_path / "cookies.json",
        key_file=hmac_key,
    )

    data = snapshot_dict(snapshot)

    assert data["day"] == "2026-08-10"
    # The requirement is JSON-serialisability for the MCP server, not any
    # particular container type: asdict leaves tuples as tuples and json
    # renders those as arrays.
    assert json.loads(json.dumps(data))["day"] == "2026-08-10"


def test_defaults_resolve_to_the_isolated_paths(data_dir: Path):
    snapshot = gather_status(now=MONDAY_NOON)

    assert snapshot.locked


def test_main_exits_one_when_locked(capsys, data_dir: Path):
    exit_code = _status.main([])

    assert exit_code == 1
    assert "state" in capsys.readouterr().out


def test_main_exits_zero_when_unlocked(
    capsys, data_dir: Path, hmac_key: Path, monkeypatch
):
    ledger = Ledger()
    add_charge(ledger, _status.local_today(), key_file=hmac_key)
    monkeypatch.setattr(_status, "load_ledger", lambda *a, **k: ledger)

    assert _status.main([]) == 0
