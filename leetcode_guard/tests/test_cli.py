"""Tests for the command line."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _cli
from leetcode_guard._auth import AuthState
from leetcode_guard._daycost import local_today
from leetcode_guard._ledger import bootstrap_entry
from leetcode_guard._ledger_io import Ledger, append, load_ledger, save_ledger
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._settings import Client
from leetcode_guard.tests._ledger_fixtures import NOW, add_charge, ledger_with_credits
from leetcode_guard.tests._net_fixtures import (
    fake_post,
    pool_result,
    problem_row,
    recent_ac_result,
    submission_row,
)

if TYPE_CHECKING:
    from pathlib import Path


def stub_client(monkeypatch: pytest.MonkeyPatch, *results: GraphQLResult) -> None:
    """Replace ``build_client`` with one wired to a scripted fake."""
    post = fake_post(*results)
    monkeypatch.setattr(
        _cli,
        "build_client",
        lambda: Client(
            post=post,
            auth=AuthState(cookies=None, note="signed out"),
            username="kuchy",
        ),
    )


def test_probe_prints_submissions_and_suggestions(monkeypatch, capsys, data_dir: Path):
    stub_client(
        monkeypatch,
        recent_ac_result([submission_row("42", "two-sum", timestamp=1_700_000_000)]),
        pool_result([problem_row("two-sum", ac_rate=57.9)], total=1),
    )

    exit_code = _cli.main(["--probe"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "username: kuchy" in out
    assert "two-sum" in out
    assert "id=42" in out
    assert "57.9% acceptance" in out
    assert "https://leetcode.com/problems/two-sum/" in out


def test_probe_exits_nonzero_when_the_probe_is_unverifiable(monkeypatch, capsys):
    stub_client(
        monkeypatch,
        GraphQLResult(transport_error="down"),
        GraphQLResult(transport_error="down"),
    )

    exit_code = _cli.main(["--probe"])
    out = capsys.readouterr().out

    assert exit_code == 2
    assert "unverifiable" in out
    assert "0 problems from none" in out


def test_probe_prints_pool_notes(monkeypatch, capsys):
    stub_client(
        monkeypatch,
        recent_ac_result([]),
        GraphQLResult(transport_error="down"),
    )

    _cli.main(["--probe"])
    out = capsys.readouterr().out

    assert "note: signed out" in out


def test_bare_invocation_opens_a_demo_lock(monkeypatch, data_dir: Path):
    """Demo is the default; --production opts out. A new locker that hard-grabs
    on its first ever run is how an afternoon gets lost."""
    built: dict = {}

    class FakeGuard:
        def __init__(self, *, demo_mode, deps):
            built["demo_mode"] = demo_mode
            built["deps"] = deps

        def run(self):
            built["ran"] = True

    stub_client(monkeypatch, recent_ac_result([]), pool_result([], total=0))
    monkeypatch.setattr(_cli, "LeetcodeGuard", FakeGuard)

    assert _cli.main([]) == 0
    assert built["demo_mode"] is True
    assert built["ran"]
    assert built["deps"].ledger_path.name == "ledger_demo.json"


def test_production_opts_out_of_demo(monkeypatch, data_dir: Path):
    built: dict = {}

    class FakeGuard:
        def __init__(self, *, demo_mode, deps):
            built["demo_mode"] = demo_mode
            built["deps"] = deps

        def run(self):
            pass

    stub_client(monkeypatch, recent_ac_result([]), pool_result([], total=0))
    monkeypatch.setattr(_cli, "LeetcodeGuard", FakeGuard)

    assert _cli.main(["--production"]) == 0
    assert built["demo_mode"] is False
    assert built["deps"].ledger_path.name == "ledger.json"


def test_production_exits_without_a_window_when_today_is_settled(
    monkeypatch, capsys, data_dir: Path, hmac_key: Path
):
    """What makes the afternoon retry free: a settled day costs milliseconds
    and draws nothing."""
    ledger = Ledger()
    add_charge(ledger, local_today(), key_file=hmac_key)
    monkeypatch.setattr(_cli, "load_ledger", lambda *a, **k: ledger)
    monkeypatch.setattr(
        _cli, "LeetcodeGuard", lambda **kwargs: pytest.fail("should not have armed")
    )

    assert _cli.main(["--production"]) == 0
    assert "already unlocked" in capsys.readouterr().out


def test_a_demo_run_wipes_its_own_ledger(monkeypatch, data_dir: Path):
    """So a demo always starts from the same place and cannot spend real
    credits or leave stale ones behind."""
    demo_ledger = data_dir / "ledger_demo.json"
    demo_ledger.write_text('{"version": 1, "entries": []}', encoding="utf-8")

    class FakeGuard:
        def __init__(self, **kwargs):
            pass

        def run(self):
            pass

    stub_client(monkeypatch, recent_ac_result([]), pool_result([], total=0))
    monkeypatch.setattr(_cli, "LeetcodeGuard", FakeGuard)

    _cli.main([])

    assert not demo_ledger.exists()


def test_status_reads_from_disk_without_touching_the_network(capsys, data_dir: Path):
    """The suite blocks real HTTP, so this passing is the proof."""
    exit_code = _cli.main(["--status"])
    out = capsys.readouterr().out

    assert exit_code == 1
    assert "day " in out
    assert "credits " in out


def test_check_prints_the_decision_trace_and_writes_nothing(
    monkeypatch, capsys, data_dir: Path
):
    ledger_file = data_dir / "ledger.json"
    stub_client(
        monkeypatch,
        recent_ac_result([submission_row("42", "two-sum")]),
    )

    exit_code = _cli.main(["--check"])
    out = capsys.readouterr().out

    assert exit_code == 1
    assert "1 existing submissions would be marked already-seen" in out
    assert "would mint 0 credits (seeding claims them all)" in out
    assert "decision   locked" in out
    assert "needed     1" in out
    assert "(nothing was written)" in out
    assert not ledger_file.exists()


def test_check_reports_an_unverifiable_probe(monkeypatch, capsys, data_dir: Path):
    stub_client(monkeypatch, GraphQLResult(transport_error="down"))

    exit_code = _cli.main(["--check"])
    out = capsys.readouterr().out

    assert exit_code == 1
    assert "probe      unverifiable" in out
    assert "would mint 0 credits" in out


def test_check_reports_an_unlocked_day(
    monkeypatch, capsys, data_dir: Path, hmac_key: Path
):
    ledger = ledger_with_credits(3, day=local_today(), key_file=hmac_key)
    # Bootstrapped, as any ledger that has ever run the gate would be. Without
    # the marker `needs_seeding` is correctly True even though credits exist.
    append(
        ledger,
        [bootstrap_entry(day=local_today(), now=NOW, seeded=0, key_file=hmac_key)],
    )
    save_ledger(data_dir / "ledger.json", ledger)
    monkeypatch.setattr(_cli, "load_ledger", lambda *a, **k: ledger)
    stub_client(monkeypatch, recent_ac_result([]))

    exit_code = _cli.main(["--check"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "decision   charged" in out
    assert "seeding" not in out


def test_check_reports_an_unreadable_integrity_key(
    monkeypatch, capsys, data_dir: Path, missing_key: Path
):
    monkeypatch.setattr(
        _cli,
        "load_ledger",
        lambda path, **kwargs: load_ledger(path, key_file=missing_key),
    )
    stub_client(monkeypatch, recent_ac_result([]))

    _cli.main(["--check"])

    assert "integrity  OFF" in capsys.readouterr().out


def test_parser_flags():
    args = _cli.build_parser().parse_args(
        ["--production", "--probe", "--status", "--check", "--verbose"]
    )

    assert args.production
    assert args.probe
    assert args.status
    assert args.check
    assert args.verbose


def test_timestamps_render_in_local_time():
    rendered = _cli._format_timestamp(0)

    assert rendered.startswith("19")


def test_a_second_concurrent_run_stands_down(monkeypatch, capsys, data_dir: Path):
    """The afternoon retry must not stack a second waiter behind the morning
    run -- that would clear the gate twice."""
    monkeypatch.setattr(_cli, "acquire_instance", lambda _path: None)

    assert _cli.main([]) == 0
    assert "already active" in capsys.readouterr().err


def test_sync_reports_what_it_did(monkeypatch, capsys, data_dir: Path):
    from leetcode_guard._sync import SyncResult

    monkeypatch.setattr(
        _cli,
        "sync_ledger",
        lambda _path: SyncResult(
            pushed=True, record_count=7, merged_in=2, reason="pushed 7, merged 2"
        ),
    )

    exit_code = _cli.main(["--sync"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "sync       pushed" in out
    assert "7 total, 2 merged in" in out


def test_sync_exits_nonzero_when_it_could_not_push(monkeypatch, capsys, data_dir: Path):
    from leetcode_guard._sync import SyncResult

    monkeypatch.setattr(
        _cli,
        "sync_ledger",
        lambda _path: SyncResult(
            pushed=False, record_count=0, merged_in=0, reason="no sync token"
        ),
    )

    assert _cli.main(["--sync"]) == 1
    assert "not pushed" in capsys.readouterr().out


def test_cache_statements_writes_the_mirror(monkeypatch, capsys, data_dir: Path):
    stub_client(
        monkeypatch,
        pool_result([problem_row("two-sum")], total=1),
        GraphQLResult(
            data={
                "question": {
                    "titleSlug": "two-sum",
                    "title": "Two Sum",
                    "difficulty": "Easy",
                    "content": "<p>text</p>",
                }
            }
        ),
    )

    exit_code = _cli.main(["--cache-statements"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "fetching 1 statements" in out
    assert "cached 1 statements" in out
    assert (data_dir / "statements_cache.json").exists()


def test_cache_statements_says_so_when_there_is_no_pool(
    monkeypatch, capsys, data_dir: Path
):
    stub_client(monkeypatch, GraphQLResult(transport_error="down"))

    assert _cli.main(["--cache-statements"]) == 1
    assert "no problems to cache" in capsys.readouterr().out


def test_cache_statements_reports_partial_failure(monkeypatch, capsys, data_dir: Path):
    stub_client(
        monkeypatch,
        pool_result([problem_row("a")], total=1),
        GraphQLResult(transport_error="down"),
    )

    assert _cli.main(["--cache-statements"]) == 1
    assert "1 unavailable" in capsys.readouterr().out


def test_production_is_free_and_silent_before_the_start_date(
    monkeypatch, capsys, data_dir: Path
):
    """The timer fires daily from install day; until the gate is in force each
    run must cost nothing -- not even a network call."""
    monkeypatch.setattr(
        _cli, "build_client", lambda: pytest.fail("must not touch the network")
    )
    monkeypatch.setattr(_cli, "GATE_START_DATE", local_today() + timedelta(days=1))

    assert _cli.main(["--production"]) == 0
    assert "gate not active until" in capsys.readouterr().out


def test_demo_ignores_the_start_date(monkeypatch, data_dir: Path):
    """So the lock can always be demonstrated, whatever the date."""
    built: dict = {}

    class FakeGuard:
        def __init__(self, **kwargs):
            built["made"] = True

        def run(self):
            pass

    monkeypatch.setattr(_cli, "GATE_START_DATE", local_today() + timedelta(days=99))
    stub_client(monkeypatch, recent_ac_result([]), pool_result([], total=0))
    monkeypatch.setattr(_cli, "LeetcodeGuard", FakeGuard)

    assert _cli.main([]) == 0
    assert built["made"]
