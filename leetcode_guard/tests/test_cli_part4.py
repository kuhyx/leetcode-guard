"""Continued from :mod:`leetcode_guard.tests.test_cli_part2`, split for the 250-line cap."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _cli
from leetcode_guard._daycost import local_today
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._sync import SyncResult
from leetcode_guard.tests._net_fixtures import (
    pool_result,
    problem_row,
    recent_ac_result,
)
from leetcode_guard.tests.test_cli import patch_cli, stub_client

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.usefixtures("data_dir")
def test_sync_exits_nonzero_when_it_could_not_push(monkeypatch, capsys):
    """--sync exits 1 and says so when the push did not happen."""
    patch_cli(
        monkeypatch,
        "sync_ledger",
        lambda _path: SyncResult(
            pushed=False, record_count=0, merged_in=0, reason="no sync token"
        ),
    )

    assert _cli.main(["--sync"]) == 1
    assert "not pushed" in capsys.readouterr().out


@pytest.mark.usefixtures("data_dir")
def test_login_exits_zero_once_the_cookies_verify(monkeypatch):
    """--login exits 0 when the login verifies."""
    patch_cli(monkeypatch, "login", lambda _path, *, timeout: bool(timeout))

    assert _cli.main(["--login"]) == 0


@pytest.mark.usefixtures("data_dir")
def test_login_exits_nonzero_when_leetcode_refuses(monkeypatch):
    """A refusal has to be visible to a shell: the whole command exists because
    a dead session used to look exactly like a live one."""
    patch_cli(monkeypatch, "login", lambda _path, *, timeout: False)

    assert _cli.main(["--login"]) == 1


def test_cache_statements_writes_the_mirror(monkeypatch, capsys, data_dir: Path):
    """--cache-statements fetches the pool and writes the statements mirror."""
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


@pytest.mark.usefixtures("data_dir")
def test_cache_statements_says_so_when_there_is_no_pool(monkeypatch, capsys):
    """An unreachable pool exits 1 with a no-problems message."""
    stub_client(monkeypatch, GraphQLResult(transport_error="down"))

    assert _cli.main(["--cache-statements"]) == 1
    assert "no problems to cache" in capsys.readouterr().out


@pytest.mark.usefixtures("data_dir")
def test_cache_statements_reports_partial_failure(monkeypatch, capsys):
    """A statement that fails to fetch is counted as unavailable and exits 1."""
    stub_client(
        monkeypatch,
        pool_result([problem_row("a")], total=1),
        GraphQLResult(transport_error="down"),
    )

    assert _cli.main(["--cache-statements"]) == 1
    assert "1 unavailable" in capsys.readouterr().out


@pytest.mark.usefixtures("data_dir")
def test_production_is_free_and_silent_before_the_start_date(monkeypatch, capsys):
    """The timer fires daily from install day; until the gate is in force each
    run must cost nothing -- not even a network call."""
    monkeypatch.setattr(
        _cli, "build_client", lambda: pytest.fail("must not touch the network")
    )
    patch_cli(monkeypatch, "GATE_START_DATE", local_today() + timedelta(days=1))

    assert _cli.main(["--production"]) == 0
    assert "gate not active until" in capsys.readouterr().out


@pytest.mark.usefixtures("data_dir")
def test_demo_ignores_the_start_date(monkeypatch):
    """So the lock can always be demonstrated, whatever the date."""
    built: dict = {}

    class FakeGuard:
        """Records that the CLI built a guard instead of opening a lock."""

        def __init__(self, **_kwargs):
            built["made"] = True

        def run(self):
            """Do nothing: the test only checks the guard was built."""

    patch_cli(monkeypatch, "GATE_START_DATE", local_today() + timedelta(days=99))
    stub_client(monkeypatch, recent_ac_result([]), pool_result([], total=0))
    patch_cli(monkeypatch, "LeetcodeGuard", FakeGuard)

    assert _cli.main([]) == 0
    assert built["made"]
