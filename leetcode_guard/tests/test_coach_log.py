"""Tests for the coach session-log reader (TODO-coach.md decision 8).

The log is being built in parallel, so the reader is tolerant by contract:
an unknown or malformed line is skipped with one warning per file, never a
crash and never a guess.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from leetcode_guard import _coach_log, _coach_view
from leetcode_guard._coach_log import read_coach, read_session

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def write_log(directory: Path, name: str, *lines: object) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(
        "\n".join(line if isinstance(line, str) else json.dumps(line) for line in lines)
        + "\n",
        encoding="utf-8",
    )
    return path


def test_a_missing_directory_is_a_known_empty_coach(tmp_path: Path):
    coach = read_coach(tmp_path / "absent")

    assert coach is not None
    assert coach["problems"] == []
    assert coach["retests_due"] == []


def test_the_default_directory_is_redirected(tmp_path: Path):
    assert _coach_log.COACH_SESSIONS_DIR.is_relative_to(tmp_path)
    coach = read_coach()
    assert coach is not None
    assert coach["problems"] == []


def test_a_full_session_is_summarised(tmp_path: Path):
    write_log(
        tmp_path,
        "2026-10-23-missing-number.jsonl",
        {"event": "req", "cluster": "bit-cancellation"},
        {"event": "req_check", "verdict": "incomplete"},
        {"event": "req_check", "verdict": "pass"},
        {"event": "rung", "rung": "H1"},
        {"event": "rung", "rung": "H0"},
        {"event": "code"},
        {"event": "postmortem"},
    )

    coach = read_coach(tmp_path)

    assert coach is not None
    bit = coach["clusters"]["bit-cancellation"]
    assert {k: bit[k] for k in ("total", "started", "solved", "next")} == {
        "total": 4,
        "started": 1,
        "solved": 1,
        "next": "single-number-iii",
    }
    assert isinstance(coach["retests_due"], list)
    assert coach["problems"] == [
        {
            "slug": "missing-number",
            "cluster": "bit-cancellation",
            "req_before_code": True,
            "max_rung": "H1",
            "revealed": False,
            "req_check": "pass",
            "day": "2026-10-23",
            # A CLI-only file: no app session, so its grades are unknown.
            "grades": None,
            "accepted": None,
        }
    ]


def test_code_before_any_req_is_recorded_as_such(tmp_path: Path):
    path = write_log(
        tmp_path,
        "2026-10-24-single-number.jsonl",
        {"event": "code"},
        {"event": "req"},
        {"event": "reveal"},
    )

    problem = read_session(path)

    assert problem is not None
    assert problem.req_before_code is False
    assert problem.revealed is True
    assert problem.max_rung is None
    assert problem.req_check is None


def test_no_code_yet_leaves_req_before_code_unknown(tmp_path: Path):
    path = write_log(tmp_path, "2026-10-24-x.jsonl", {"event": "req"})

    problem = read_session(path)

    assert problem is not None
    assert problem.req_before_code is None


def test_a_name_without_a_date_keeps_the_whole_stem(tmp_path: Path):
    path = write_log(tmp_path, "two-sum.jsonl", {"event": "req"})

    problem = read_session(path)

    assert problem is not None
    assert (problem.slug, problem.day) == ("two-sum", None)


def test_a_dated_shape_with_an_impossible_date_keeps_the_whole_stem(tmp_path: Path):
    path = write_log(tmp_path, "2026-13-45-x.jsonl", {"event": "req"})

    problem = read_session(path)

    assert problem is not None
    assert (problem.slug, problem.day) == ("2026-13-45-x", None)


def test_unknown_lines_are_skipped_with_one_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    path = write_log(
        tmp_path,
        "2026-10-23-a.jsonl",
        "{not json",
        [1, 2],
        {"event": "teleport"},
        {"event": "rung", "rung": "H9"},
        {"event": "req_check", "verdict": "maybe"},
        {"event": "rung", "rung": "H2"},
        {"no": "event"},
        "",
    )

    problem = read_session(path)

    assert problem is not None
    assert problem.max_rung == "H2"
    warnings = [r for r in caplog.records if "skipped" in r.getMessage()]
    assert len(warnings) == 1
    assert "5 unknown" in warnings[0].getMessage()
    assert "line 1 is not JSON" in caplog.text


def test_a_blank_cluster_is_ignored(tmp_path: Path):
    path = write_log(
        tmp_path,
        "2026-10-23-a.jsonl",
        {"event": "req", "cluster": ""},
        {"event": "code", "cluster": "two-pointers"},
    )

    problem = read_session(path)

    assert problem is not None
    assert problem.cluster == "two-pointers"


def test_an_unreadable_file_is_skipped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    path = tmp_path / "2026-10-23-a.jsonl"
    path.mkdir(parents=True)

    assert read_session(path) is None
    coach = read_coach(tmp_path)
    assert coach is not None
    assert coach["problems"] == []
    assert coach["retests_due"] == []
    assert coach["clusters"]["intervals"]["started"] == 0
    assert "unreadable" in caplog.text


def test_due_retests_come_from_the_coach(tmp_path: Path):
    write_log(
        tmp_path,
        "2026-01-02-missing-number.jsonl",
        {"event": "code"},
        {"event": "postmortem"},
    )

    coach = read_coach(tmp_path)

    assert coach is not None
    assert [(r["slug"], r["stage"], r["due"]) for r in coach["retests_due"]] == [
        ("missing-number", 1, "2026-01-05")
    ]


def test_a_failing_coach_derivation_is_unknown_with_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    def boom(_folder: Path) -> object:
        message = "clusters.json is broken"
        raise ValueError(message)

    tmp_path.mkdir(exist_ok=True)
    monkeypatch.setattr(_coach_view.coach_progress, "cluster_progress", boom)

    coach = read_coach(tmp_path)

    assert coach is not None
    assert coach["clusters"] is None
    assert coach["retests_due"] == []
    assert "clusters.json is broken" in caplog.text
