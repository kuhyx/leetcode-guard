"""Continued from :mod:`leetcode_guard.tests.test_cli`, split for the 250-line cap."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _cli
from leetcode_guard.tests._net_fixtures import (
    pool_result,
    problem_row,
    recent_ac_result,
    submission_row,
)

if TYPE_CHECKING:
    from pathlib import Path


from leetcode_guard.tests.test_cli import (
    _seeded_ledger,
    patch_cli,
    stub_client,
)


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
    patch_cli(monkeypatch, "LeetcodeGuard", FakeGuard)

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
    patch_cli(monkeypatch, "LeetcodeGuard", FakeGuard)
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
    patch_cli(monkeypatch, "LeetcodeGuard", FakeGuard)

    _cli.main([])

    assert not demo_ledger.exists()
