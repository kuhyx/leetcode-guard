"""The shared wording, and the report that both surfaces print from."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from leetcode_guard import _status_projection
from leetcode_guard._progress import write_progress_cache
from leetcode_guard._projection import Position, project
from leetcode_guard._projection_text import (
    UNKNOWN_PROGRESS,
    is_count_line,
    progress_lines,
    projection_lines,
)
from leetcode_guard._status import gather_status
from leetcode_guard._status_projection import (
    PAST_TARGET,
    UNREADABLE_TARGET,
    ProjectionInputs,
    build_report,
    cached_progress,
    fetch_live_progress,
    position_of,
)
from leetcode_guard.tests._guard_factories import SIGNED_OUT
from leetcode_guard.tests.test_projection import SAT, never_free, position, progress

if TYPE_CHECKING:
    from pathlib import Path


def test_unknown_progress_is_one_honest_line():
    assert progress_lines(None) == [UNKNOWN_PROGRESS]


def test_progress_lines_are_aligned_and_dated():
    lines = progress_lines(progress())

    assert lines[0] == "Easy      55 / 965   (  5.7 %)   910 left"
    assert lines[3] == "All       55 / 4055  (  1.4 %)  4000 left"
    assert lines[4].startswith("LeetCode profile figures, as of ")
    assert [is_count_line(line) for line in lines] == [True] * 4 + [False]


def test_projection_lines_show_the_working_and_the_counts():
    result = project(
        date(2026, 9, 26), position(), is_free=never_free, progress=progress()
    )

    lines = projection_lines(result, progress())

    assert lines[0] == (
        "By 26.09.2026, counting from 20.09.2026: 7 gated day(s), 0 free."
    )
    assert (
        lines[1]
        == "20 (day prices) + 14 (debt) - 0 (banked) = 34 new problem(s) to solve."
    )
    assert "demand 27 by then and leave 7 of the debt" in lines[2]
    assert lines[3] == "Easy      89 / 965   (  9.2 %)   876 left"
    assert lines[6] == "All       89 / 4055  (  2.2 %)  3966 left"
    assert lines[7].startswith("Assumes every new solve")


def test_a_horizon_that_clears_the_debt_says_so():
    result = project(date(2026, 12, 31), position(), is_free=never_free, progress=None)

    lines = projection_lines(result, None)

    assert "the same 334 by then (debt fully repaid" in lines[2]
    assert lines[3] == "Per-difficulty projection needs the solved counts above."
    assert len(lines) == 4


def test_the_report_rejects_an_unreadable_date(data_dir: Path, hmac_key: Path):
    snapshot = gather_status(ledger_path=data_dir / "ledger.json", key_file=hmac_key)

    report = build_report(snapshot, progress(), ProjectionInputs("banana"))

    assert report.projection is None
    assert report.then_lines() == [UNREADABLE_TARGET]
    assert report.now_lines() == progress_lines(progress())


def test_the_report_rejects_a_date_behind_today(data_dir: Path, hmac_key: Path):
    snapshot = gather_status(ledger_path=data_dir / "ledger.json", key_file=hmac_key)

    report = build_report(snapshot, None, ProjectionInputs("01.01.2000"))

    assert report.then_lines() == [PAST_TARGET]


def test_the_report_projects_from_the_snapshot(data_dir: Path, hmac_key: Path):
    snapshot = gather_status(ledger_path=data_dir / "ledger.json", key_file=hmac_key)

    report = build_report(snapshot, progress(), ProjectionInputs("31.12.2999"))

    assert report.projection is not None
    assert report.projection.target == date(2999, 12, 31)
    assert (
        report.then_lines()[0] == "Prices: Tue/Wed/Thu cost 2, Mon/Fri/Sat/Sun cost 4."
    )
    assert report.then_lines()[1].startswith("By 31.12.2999")
    assert report.goal_lines() == []


def test_a_problem_free_report_with_no_projection_falls_back_to_the_generic_line():
    report = _status_projection.ProjectionReport(None, None)

    assert report.then_lines() == [UNREADABLE_TARGET]


def test_position_of_lifts_the_gate_facts(data_dir: Path, hmac_key: Path):
    snapshot = gather_status(ledger_path=data_dir / "ledger.json", key_file=hmac_key)

    lifted = position_of(snapshot)

    assert lifted == Position(
        today=date.fromisoformat(snapshot.day),
        charged_today=snapshot.charged_today,
        available=snapshot.available,
        debt_outstanding=snapshot.debt_outstanding,
    )


def test_position_of_falls_back_to_today_on_a_malformed_day(
    data_dir: Path, hmac_key: Path, monkeypatch
):
    snapshot = gather_status(ledger_path=data_dir / "ledger.json", key_file=hmac_key)
    broken = snapshot.__class__(**{**snapshot.__dict__, "day": "not-a-day"})
    monkeypatch.setattr(_status_projection, "local_today", lambda: SAT)

    assert position_of(broken).today == SAT


def test_free_days_reach_the_projection(data_dir: Path, hmac_key: Path, monkeypatch):
    snapshot = gather_status(ledger_path=data_dir / "ledger.json", key_file=hmac_key)
    monkeypatch.setattr(_status_projection.freedays, "is_free_day", lambda _day: True)

    report = build_report(snapshot, None, ProjectionInputs("31.12.2999"))

    assert report.projection is not None
    assert report.projection.gated_days == 0


def test_cached_progress_reads_the_redirected_mirror(data_dir: Path):
    assert cached_progress() is None
    write_progress_cache(data_dir / "progress_cache.json", progress())

    assert cached_progress() == progress()


def test_the_live_fetch_refreshes_the_mirror(monkeypatch, data_dir: Path):
    from leetcode_guard._leetcode import GraphQLResult
    from leetcode_guard._settings import Client
    from leetcode_guard.tests._net_fixtures import fake_post
    from leetcode_guard.tests.test_progress import payload

    post = fake_post(GraphQLResult(data=payload()))
    monkeypatch.setattr(
        _status_projection,
        "build_client",
        lambda: Client(post=post, username="kuchy", auth=SIGNED_OUT),
    )

    live = fetch_live_progress()

    assert live is not None
    assert live.solved["Easy"] == 55
    assert (data_dir / "progress_cache.json").exists()


def test_a_failed_live_fetch_with_no_mirror_is_none_and_logged(
    monkeypatch, data_dir: Path, caplog
):
    from leetcode_guard._leetcode import GraphQLResult
    from leetcode_guard._settings import Client
    from leetcode_guard.tests._net_fixtures import fake_post

    post = fake_post(GraphQLResult(transport_error="offline"))
    monkeypatch.setattr(
        _status_projection,
        "build_client",
        lambda: Client(post=post, username="kuchy", auth=SIGNED_OUT),
    )

    with caplog.at_level("WARNING"):
        assert fetch_live_progress() is None

    assert "no solve progress available" in caplog.text
