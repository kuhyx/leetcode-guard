"""Tests for the command line."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _cli, _cli_commands
from leetcode_guard._auth import AuthState
from leetcode_guard._daycost import local_today
from leetcode_guard._ledger_entries import bootstrap_entry
from leetcode_guard._ledger_io import Ledger, append, load_ledger, save_ledger
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._settings import Client
from leetcode_guard.tests._ledger_fixtures import NOW, add_charge
from leetcode_guard.tests._net_fixtures import (
    fake_post,
    pool_result,
    problem_row,
    recent_ac_result,
    submission_row,
)

if TYPE_CHECKING:
    from pathlib import Path


def patch_cli(monkeypatch: pytest.MonkeyPatch, name: str, value: object) -> None:
    """Rebind ``name`` on whichever CLI module actually reads it.

    The command line is two modules since the 250-line split -- the parser and
    the lock command in ``_cli``, everything that prints and exits in
    ``_cli_commands`` -- and several names are imported by both. Patching only
    one leaves the other pointed at the real thing, which for `build_client`
    means a test that looks stubbed and reaches the network.
    """
    patched = False
    for module in (_cli, _cli_commands):
        if hasattr(module, name):
            monkeypatch.setattr(module, name, value)
            patched = True
    if not patched:
        message = f"neither CLI module defines {name!r}"
        raise AssertionError(message)


def stub_client(monkeypatch: pytest.MonkeyPatch, *results: GraphQLResult) -> None:
    """Replace ``build_client`` with one wired to a scripted fake."""
    post = fake_post(*results)
    patch_cli(
        monkeypatch,
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
    patch_cli(monkeypatch, "LeetcodeGuard", FakeGuard)

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
    patch_cli(monkeypatch, "LeetcodeGuard", FakeGuard)
    # Pre-seeded: the run that *creates* a ledger deliberately returns before
    # building a guard at all, so a fresh one would never reach FakeGuard.
    _seeded_ledger(data_dir)

    assert _cli.main(["--production"]) == 0
    assert built["demo_mode"] is False
    assert built["deps"].ledger_path.name == "ledger.json"


def _seeded_ledger(data_dir: Path) -> None:
    """Write a ledger that already carries its bootstrap marker."""
    ledger = Ledger()
    append(ledger, [bootstrap_entry(day=local_today(), now=NOW, seeded=0)])
    save_ledger(data_dir / "ledger.json", ledger)


def test_the_run_that_creates_the_ledger_does_not_arm(monkeypatch, capsys, data_dir):
    """Seeding marks the whole recent feed already-seen, so the gate it hands
    over needs a solve that has not happened yet -- the 2026-08-05 arm. The run
    defers instead of writing a charge, because a charge for today is the key
    ``decide`` unlocks on and would make ``rm ledger.json`` worth a free day."""
    built: dict = {}

    class FakeGuard:
        def __init__(self, **kwargs):
            built["built"] = True

        def run(self):
            pass

    stub_client(
        monkeypatch,
        recent_ac_result([submission_row("42", "two-sum")]),
        pool_result([], total=0),
    )
    patch_cli(monkeypatch, "LeetcodeGuard", FakeGuard)

    assert _cli.main(["--production"]) == 0

    assert "built" not in built, "the seeding run must not arm a lock"
    assert "not arming this run" in capsys.readouterr().out
    ledger = load_ledger(data_dir / "ledger.json")
    assert ledger.has("ac:42")
    assert not ledger.of_kind("charge"), "a deferral must not be a charge"


def test_production_exits_without_a_window_when_today_is_settled(
    monkeypatch, capsys, data_dir: Path, hmac_key: Path
):
    """What makes the afternoon retry free: a settled day costs milliseconds
    and draws nothing."""
    ledger = Ledger()
    add_charge(ledger, local_today(), key_file=hmac_key)
    patch_cli(monkeypatch, "load_ledger", lambda *a, **k: ledger)
    monkeypatch.setattr(
        _cli, "LeetcodeGuard", lambda **kwargs: pytest.fail("should not have armed")
    )

    assert _cli.main(["--production"]) == 0
    assert "already unlocked" in capsys.readouterr().out
