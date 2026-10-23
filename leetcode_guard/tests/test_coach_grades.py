"""The app's events in the Coach-tab reader (DOCS-coach-relay.md section 5).

Four new event names, each with a shape rule, and per-problem ``grades`` /
``accepted`` from the file's latest ``session_start`` onward. A CLI-only file
says nothing about grades: ``None``, never zero.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import pytest

from leetcode_coach import session_log
from leetcode_guard import _coach_grades, _coach_log

if TYPE_CHECKING:
    from pathlib import Path


def _write(tmp_path: Path, *events: dict[str, Any]) -> Path:
    path = tmp_path / "2026-10-23-missing-number.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return path


def _grade(step: object, grade: str, **extra: object) -> dict[str, Any]:
    return {"event": "grade", "step": step, "grade": grade, "via": "haiku", **extra}


def test_the_reader_knows_every_event_the_writer_may_write() -> None:
    assert session_log.EVENTS == _coach_log.EVENTS


@pytest.mark.parametrize(
    ("event", "ok"),
    [
        ({"event": "session_start", "source": "app"}, True),
        (_grade(1, "pass"), True),
        (_grade(5, "fail"), True),
        (_grade(0, "pass"), False),
        (_grade(6, "pass"), False),
        (_grade(True, "pass"), False),
        (_grade("1", "pass"), False),
        (_grade(2, "great"), False),
        ({"event": "chat", "role": "kuhy", "text": "hi"}, True),
        ({"event": "chat", "role": "coach", "text": "hi"}, True),
        ({"event": "chat", "role": "system", "text": "hi"}, False),
        ({"event": "session_end", "reason": "done"}, True),
        ({"event": "session_end", "reason": "reveal"}, True),
        ({"event": "session_end", "reason": "ended"}, True),
        ({"event": "session_end", "reason": "bored"}, False),
    ],
)
def test_shape_rules(event: dict[str, Any], ok: bool) -> None:
    assert _coach_log._well_formed(event) is ok


def test_a_cli_only_file_has_unknown_grades(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = _write(tmp_path, {"event": "req"}, _grade(1, "pass"))
    with caplog.at_level(logging.WARNING):
        problem = _coach_log.read_session(path)
    assert problem is not None
    assert problem.grades is None
    assert problem.accepted is None
    assert "skipped" not in caplog.text


def test_grades_come_from_the_latest_session_only(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        {"event": "session_start", "sid": "a"},
        _grade(1, "pass"),
        _grade(4, "pass", via="accepted"),
        {"event": "session_start", "sid": "b"},
        _grade(1, "fail"),
        _grade(1, "partial"),
        _grade(1, "partial", forced=True),
        _grade(2, "partial", via="unverified"),
        _grade(2, "pass"),
        {"event": "session_end", "reason": "ended"},
    )
    problem = _coach_log.read_session(path)
    assert problem is not None
    assert problem.grades == {
        "constraint": {
            "grade": "partial",
            "attempts": 2,
            "forced": True,
            "via": "haiku",
        },
        "requirements": {
            "grade": "pass",
            "attempts": 2,
            "forced": False,
            "via": "haiku",
        },
        "toolbox": None,
        "postmortem": None,
    }
    assert problem.accepted is False


def test_step_four_passed_is_accepted() -> None:
    events = [{"event": "session_start"}, _grade(4, "pass", via="accepted")]
    grades, accepted = _coach_grades.grades(events)
    assert accepted is True
    assert grades is not None
    assert set(grades) == {"constraint", "requirements", "toolbox", "postmortem"}


def test_grades_ride_in_the_snapshot_rows(tmp_path: Path) -> None:
    _write(tmp_path, {"event": "session_start"}, _grade(3, "pass", via="toolbox"))
    coach = _coach_log.read_coach(tmp_path)
    assert coach is not None
    row = coach["problems"][0]
    assert row["grades"]["toolbox"]["via"] == "toolbox"
    assert row["accepted"] is False


def test_a_force_alone_is_no_try() -> None:
    events = [{"event": "session_start"}, _grade(2, "fail", forced=True)]
    grades, _accepted = _coach_grades.grades(events)
    assert grades is not None
    assert grades["requirements"] == {
        "grade": "fail",
        "attempts": 0,
        "forced": True,
        "via": "haiku",
    }
