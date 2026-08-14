"""Tests for the command line."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _cli
from leetcode_guard._auth import AuthState
from leetcode_guard._daycost import local_today
from leetcode_guard._ledger import bootstrap_entry
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
    monkeypatch.setattr(_cli, "LeetcodeGuard", FakeGuard)

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
    monkeypatch.setattr(_cli, "load_ledger", lambda *a, **k: ledger)
    monkeypatch.setattr(
        _cli, "LeetcodeGuard", lambda **kwargs: pytest.fail("should not have armed")
    )

    assert _cli.main(["--production"]) == 0
    assert "already unlocked" in capsys.readouterr().out


def test_the_recent_feed_hides_solved_problems_even_with_no_ledger(
    monkeypatch, data_dir: Path
):
    """A screenshot of the demo surface caught this one.

    The demo deletes its ledger on every run to force a genuinely fresh solve,
    which left `solved_slugs` empty and put two problems solved days earlier
    back at the top of the list -- the exact defect being fixed, reappearing on
    the one surface a human actually looks at. The recent-AC probe is unioned
    in because it is the same feed the ledger is built from, needs no cookies,
    and was fetched seconds earlier.
    """
    captured: dict[str, object] = {}

    class FakeGuard:
        def __init__(self, **kwargs):
            captured["pool"] = kwargs["deps"].pool

        def run(self):
            pass

    stub_client(
        monkeypatch,
        recent_ac_result([submission_row("1", "already-solved")]),
        pool_result(
            [problem_row("already-solved"), problem_row("still-open")], total=2
        ),
    )
    monkeypatch.setattr(_cli, "LeetcodeGuard", FakeGuard)

    _cli.main([])

    pool = captured["pool"]
    assert [p.title_slug for p in pool.problems] == ["still-open"]


@pytest.mark.parametrize("production", [True, False])
def test_the_lock_is_wired_to_the_right_paths_for_its_mode(
    monkeypatch, data_dir: Path, *, production: bool
):
    """Pin every GuardDeps field, not just the one that already broke.

    The solved-problem bug lived here: each module was correct in isolation and
    the defect was in how `_run_lock` composed them, so a suite that only
    exercised modules could not see it. Only `pool` was asserted before, and
    only because a screenshot caught it -- the other six were free to be wired
    to the wrong thing. A demo pointed at the real ledger would spend real
    credits; a production run pointed at the demo ledger would never gate.
    """
    captured: dict[str, object] = {}

    class FakeGuard:
        def __init__(self, **kwargs):
            captured["deps"] = kwargs["deps"]
            captured["demo_mode"] = kwargs["demo_mode"]

        def run(self):
            pass

    stub_client(
        monkeypatch,
        recent_ac_result([submission_row("1", "solved-already")]),
        pool_result([problem_row("still-open")], total=1),
    )
    monkeypatch.setattr(_cli, "LeetcodeGuard", FakeGuard)
    if production:
        # The run that creates a ledger defers before building a guard at all.
        _seeded_ledger(data_dir)

    _cli.main(["--production"] if production else [])

    deps = captured["deps"]
    assert captured["demo_mode"] is not production
    # The two that decide whether a run can spend or earn anything real.
    assert deps.ledger_path == (
        _cli.LEDGER_FILE if production else _cli.DEMO_LEDGER_FILE
    )
    assert deps.escape_path == (
        _cli.ESCAPE_HISTORY_FILE if production else _cli.DEMO_ESCAPE_HISTORY_FILE
    )
    assert deps.ledger_path != deps.escape_path
    # A demo must never push to the shared sync repo.
    assert deps.sync_on_close is production
    # And the live data the surface renders from reaches it intact.
    assert deps.username == "kuchy"
    assert deps.probe.submissions[0].title_slug == "solved-already"
    assert [p.title_slug for p in deps.pool.problems] == ["still-open"]


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
