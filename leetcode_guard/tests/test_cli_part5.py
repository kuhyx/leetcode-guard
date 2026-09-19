"""Continued from :mod:`leetcode_guard.tests.test_cli_part4`: the projection flag
and the solve-progress mirror."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard import _cli, _cli_commands
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._progress import read_progress_cache
from leetcode_guard._status import gather_status
from leetcode_guard._sync import SyncResult
from leetcode_guard.tests._net_fixtures import pool_result, recent_ac_result
from leetcode_guard.tests.test_cli import patch_cli, stub_client
from leetcode_guard.tests.test_progress import payload
from leetcode_guard.tests.test_projection import progress

if TYPE_CHECKING:
    from pathlib import Path


def test_status_without_by_never_fetches(monkeypatch, capsys, data_dir: Path):
    monkeypatch.setattr(
        _cli_commands,
        "fetch_live_progress",
        lambda: (_ for _ in ()).throw(AssertionError),
    )

    _cli.main(["--status"])

    assert "solved now" not in capsys.readouterr().out


def test_status_by_prints_the_counts_and_the_projection(monkeypatch, capsys, data_dir):
    monkeypatch.setattr(_cli_commands, "fetch_live_progress", progress)
    expected = 1 if gather_status().locked else 0

    exit_code = _cli.main(["--status", "--by", "31.12.2999"])
    out = capsys.readouterr().out

    assert exit_code == expected
    assert "solved now" in out
    assert "  Easy      55 / 965   (  5.7 %)   910 left" in out
    assert "by 31.12.2999" in out
    assert "By 31.12.2999, counting from" in out
    assert "new problem(s) to solve." in out


def test_status_by_with_nothing_known_still_prints_the_working(
    monkeypatch, capsys, data_dir
):
    monkeypatch.setattr(_cli_commands, "fetch_live_progress", lambda: None)

    _cli.main(["--status", "--by", "31.12.2999"])
    out = capsys.readouterr().out

    assert "Solved counts unknown" in out
    assert "Per-difficulty projection needs the solved counts above." in out


def test_status_by_rejects_an_unusable_date_with_exit_2(monkeypatch, capsys, data_dir):
    monkeypatch.setattr(_cli_commands, "fetch_live_progress", progress)

    assert _cli.main(["--status", "--by", "banana"]) == 2
    assert "Not a date" in capsys.readouterr().out


def test_sync_refreshes_the_mirror_before_pushing(monkeypatch, capsys, data_dir):
    order: list[str] = []
    monkeypatch.setattr(
        _cli_commands, "fetch_live_progress", lambda: order.append("progress")
    )

    def fake_sync(_path):
        order.append("sync")
        return SyncResult(pushed=True, record_count=1, merged_in=0, reason="ok")

    patch_cli(monkeypatch, "sync_ledger", fake_sync)

    assert _cli.main(["--sync"]) == 0
    assert order == ["progress", "sync"]


def test_a_production_run_mirrors_the_profile_counts(monkeypatch, data_dir: Path):
    """The lock run is online anyway, so the window has a figure before it
    fetches its own. The order matters: the probe first, then progress, then
    the pool -- which is the order the fake answers in."""
    from leetcode_guard.tests.test_cli import _seeded_ledger

    class FakeGuard:
        def __init__(self, **_kwargs):
            pass

        def run(self):
            pass

    stub_client(
        monkeypatch,
        recent_ac_result([]),
        GraphQLResult(data=payload()),
        pool_result([], total=0),
    )
    patch_cli(monkeypatch, "LeetcodeGuard", FakeGuard)
    _seeded_ledger(data_dir)

    assert _cli.main(["--production"]) == 0

    mirrored = read_progress_cache(data_dir / "progress_cache.json")
    assert mirrored is not None
    assert mirrored.solved["Easy"] == 55


def test_a_demo_run_leaves_the_mirror_alone(monkeypatch, data_dir: Path):
    class FakeGuard:
        def __init__(self, **_kwargs):
            pass

        def run(self):
            pass

    stub_client(
        monkeypatch,
        recent_ac_result([]),
        GraphQLResult(data=payload()),
        pool_result([], total=0),
    )
    patch_cli(monkeypatch, "LeetcodeGuard", FakeGuard)

    assert _cli.main([]) == 0

    assert not (data_dir / "progress_cache.json").exists()
