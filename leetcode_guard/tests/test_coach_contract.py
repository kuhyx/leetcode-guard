"""The two-way contract with the leetcode_coach library (~/src/utils).

The library writes the session log and reaches three read-only guard helpers;
the guard reads that log and must stay what the library's bridge expects.
"""

from __future__ import annotations

import importlib
import re
from typing import TYPE_CHECKING

import pytest

from leetcode_coach import guard_bridge, session_log
from leetcode_guard import _coach_log

if TYPE_CHECKING:
    from pathlib import Path

HELPERS = {
    guard_bridge.SETTINGS: "build_client",
    guard_bridge.LIVE_SOLVED: "check_solved",
    guard_bridge.SUBMISSIONS: "fetch_recent_ac",
    guard_bridge.SNAPSHOT_AUTH: "connect",
}
DENIED = re.compile(
    r"_ledger.*|_balance|_debt|_harvest.*|_gate.*|_sync.*|_lock.*|_breakglass"
    r"|_escape.*|_snapshot_push"
)


@pytest.mark.parametrize(("module", "name"), sorted(HELPERS.items()))
def test_every_helper_the_coach_borrows_still_exists(module: str, name: str) -> None:
    """Each helper the coach borrows is still callable and lives in an allowed module."""
    assert callable(getattr(importlib.import_module(module), name))
    assert not DENIED.fullmatch(module.split(".")[1])


def test_the_coach_names_no_other_guard_module() -> None:
    """The coach's allow-list names exactly the borrowed helper modules."""
    assert set(HELPERS) == guard_bridge.ALLOWED


def test_the_status_reader_understands_what_the_coach_writes(tmp_path: Path) -> None:
    """A log written by the coach reads back as the expected CoachProblem."""
    path = tmp_path / "2026-10-23-missing-number.jsonl"
    session_log.append(path, "req", text="req: x", cluster="bit-cancellation")
    session_log.append(path, "req_check", verdict="incomplete", missing=["p"])
    session_log.append(path, "code", req_incomplete=True)
    session_log.append(path, "rung", rung="H2")
    problem = _coach_log.read_session(path)
    assert problem == _coach_log.CoachProblem(
        slug="missing-number",
        cluster="bit-cancellation",
        req_before_code=True,
        max_rung="H2",
        revealed=False,
        req_check="incomplete",
        day="2026-10-23",
    )


def test_a_sql_shape_reads_like_a_req_list(tmp_path: Path) -> None:
    """A SQL shape requirement counts as requirements before code."""
    path = tmp_path / "2026-11-02-reformat-department-table.jsonl"
    session_log.append(path, "req", text="shape: columns id, one row per id")
    session_log.append(path, "req_check", verdict="pass", missing=[], via="shape")
    session_log.append(path, "code")
    problem = _coach_log.read_session(path)
    assert problem is not None
    assert (problem.req_check, problem.req_before_code) == ("pass", True)


def test_the_app_session_grades_round_trip(tmp_path: Path) -> None:
    """Grades the coach writes read back as an accepted problem."""
    path = tmp_path / "2026-10-23-missing-number.jsonl"
    session_log.append(path, "session_start", sid="s1")
    for step, grade in (
        (1, "fail"),
        (2, "pass"),
        (3, "pass"),
        (4, "pass"),
        (5, "pass"),
    ):
        session_log.append(path, "grade", step=step, grade=grade, forced=False)
    problem = _coach_log.read_session(path)
    assert problem is not None
    assert problem.accepted is True
    assert problem.grades is not None
    assert problem.grades["requirements"]["grade"] == "pass"
