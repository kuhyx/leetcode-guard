"""Tests for the command line: --status, --check, --sync and the caches.

The lock-arming half is in ``test_cli.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _cli
from leetcode_guard._cli_commands import _format_timestamp
from leetcode_guard._daycost import day_cost, local_today
from leetcode_guard._ledger_entries import bootstrap_entry
from leetcode_guard._ledger_io import append, load_ledger, save_ledger
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._sync import SyncResult
from leetcode_guard.tests._cli_fixtures import assert_production_exits_unarmed
from leetcode_guard.tests._ledger_fixtures import NOW, ledger_paying_for_today
from leetcode_guard.tests._net_fixtures import (
    recent_ac_result,
    submission_row,
)
from leetcode_guard.tests.test_cli import patch_cli, stub_client

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.usefixtures("data_dir")
def test_status_reads_from_disk_without_touching_the_network(capsys):
    """The suite blocks real HTTP, so this passing is the proof."""
    exit_code = _cli.main(["--status"])
    out = capsys.readouterr().out

    assert exit_code == 1
    assert "day " in out
    assert "credits " in out


def test_check_prints_the_decision_trace_and_writes_nothing(
    monkeypatch, capsys, data_dir: Path
):
    """--check shows how it would decide, then leaves the ledger unwritten."""
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
    # Derived, not hardcoded: `--check` reads the real clock, and a weekend day
    # costs two credits. Asserting "needed 1" made this test fail every
    # Saturday and Sunday for reasons that had nothing to do with the code.
    assert f"needed     {day_cost(local_today())}" in out
    assert "(nothing was written)" in out
    assert not ledger_file.exists()


@pytest.mark.usefixtures("data_dir")
def test_check_reports_an_unverifiable_probe(monkeypatch, capsys):
    """A probe that cannot reach LeetCode is shown as unverifiable, minting nothing."""
    stub_client(monkeypatch, GraphQLResult(transport_error="down"))

    exit_code = _cli.main(["--check"])
    out = capsys.readouterr().out

    assert exit_code == 1
    assert "probe      unverifiable" in out
    assert "would mint 0 credits" in out


def test_check_reports_an_unlocked_day(
    monkeypatch, capsys, data_dir: Path, hmac_key: Path
):
    """A bootstrapped ledger whose credit pays for today reads as charged."""
    ledger = ledger_paying_for_today(key_file=hmac_key)
    # Bootstrapped, as any ledger that has ever run the gate would be. Without
    # the marker `needs_seeding` is correctly True even though credits exist.
    append(
        ledger,
        [bootstrap_entry(day=local_today(), now=NOW, seeded=0, key_file=hmac_key)],
    )
    save_ledger(data_dir / "ledger.json", ledger)
    patch_cli(monkeypatch, "load_ledger", lambda *a, **k: ledger)
    stub_client(monkeypatch, recent_ac_result([]))

    exit_code = _cli.main(["--check"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "decision   charged" in out
    assert "seeding" not in out


@pytest.mark.usefixtures("data_dir")
def test_check_reports_an_unreadable_integrity_key(
    monkeypatch, capsys, missing_key: Path
):
    """A missing signing key shows up as integrity OFF in --check."""
    patch_cli(
        monkeypatch,
        "load_ledger",
        lambda path, **kwargs: load_ledger(path, key_file=missing_key),
    )
    stub_client(monkeypatch, recent_ac_result([]))

    _cli.main(["--check"])

    assert "integrity  OFF" in capsys.readouterr().out


def test_parser_flags():
    """Every documented flag parses to its own attribute."""
    args = _cli.build_parser().parse_args(
        ["--production", "--probe", "--status", "--check", "--verbose"]
    )

    assert args.production
    assert args.probe
    assert args.status
    assert args.check
    assert args.verbose


def test_timestamps_render_in_local_time():
    """Epoch zero renders as a 19xx local date, not a raw number."""
    rendered = _format_timestamp(0)

    assert rendered.startswith("19")


@pytest.mark.usefixtures("data_dir")
def test_a_second_concurrent_run_stands_down(monkeypatch, capsys):
    """The afternoon retry must not stack a second waiter behind the morning
    run -- that would clear the gate twice."""
    patch_cli(monkeypatch, "acquire_instance", lambda _path: None)

    assert _cli.main([]) == 0
    assert "already active" in capsys.readouterr().err


@pytest.mark.usefixtures("data_dir")
def test_sync_reports_what_it_did(monkeypatch, capsys):
    """--sync prints the push and the record and merge counts."""
    patch_cli(
        monkeypatch,
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


def test_production_persists_the_charge_when_banked_credit_pays_for_today(
    monkeypatch, capsys, data_dir: Path, hmac_key: Path
):
    """The timer path must debit the bank, not just report it. Without the
    write, a day paid from credit leaves no charge behind and reads, later,
    as a day that was never settled."""
    ledger = ledger_paying_for_today(key_file=hmac_key)
    ledger_path = data_dir / "ledger.json"
    patch_cli(monkeypatch, "LEDGER_FILE", ledger_path)
    patch_cli(monkeypatch, "load_ledger", lambda *a, **k: ledger)
    assert_production_exits_unarmed(monkeypatch, capsys)
    on_disk = load_ledger(ledger_path)
    assert on_disk.has(f"charge:{local_today().isoformat()}")
