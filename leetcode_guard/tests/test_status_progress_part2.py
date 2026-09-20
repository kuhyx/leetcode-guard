"""Continued from :mod:`leetcode_guard.tests.test_status_progress`: the goal
inputs, their complaints, and what the section draws for a what-if."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._status_progress import ProjectionControls, section_progress
from leetcode_guard._status_projection import (
    BAD_PRICE,
    GOAL_NEEDS_COUNTS,
    ProjectionInputs,
    bad_goal,
    build_report,
    unknown_difficulty,
)
from leetcode_guard.tests.test_projection import progress
from leetcode_guard.tests.test_status_progress import (
    CONFIG,
    label_texts,
    snapshot_for,
)
from leetcode_guard.tests.test_status_view_part3 import a_root

if TYPE_CHECKING:
    from pathlib import Path


def red_lines(tk_mock) -> list[str]:
    return [
        call.kwargs["text"]
        for call in tk_mock.Label.call_args_list
        if call.kwargs.get("fg") == CONFIG.palette.danger
    ]


def draw(snapshot, inputs: ProjectionInputs, tk_mock, progress_=None):
    controls = ProjectionControls(
        inputs=inputs,
        report=build_report(snapshot, progress_, inputs),
        on_project=lambda _inputs: None,
    )
    section_progress(a_root(tk_mock), CONFIG, controls)


def test_a_goal_draws_its_lines_after_the_projection(data_dir: Path, hmac_key, tk_mock):
    inputs = ProjectionInputs("31.12.2999", "2", {"Easy": "100", "Medium": ""})

    draw(snapshot_for(data_dir, hmac_key), inputs, tk_mock, progress())

    texts = label_texts(tk_mock)
    assert "Goal: Easy 100 (45 more)." in texts
    assert texts.index("Goal: Easy 100 (45 more).") > texts.index(
        "Prices: Tue/Wed/Thu cost 2, Mon/Fri/Sat/Sun cost 4."
    )
    assert red_lines(tk_mock) == []


def test_a_bad_price_is_one_red_line_and_no_projection(data_dir, hmac_key, tk_mock):
    draw(snapshot_for(data_dir, hmac_key), ProjectionInputs("31.12.2999", "x"), tk_mock)

    assert red_lines(tk_mock) == [BAD_PRICE]
    assert not any(t.startswith("By ") for t in label_texts(tk_mock))


def test_a_bad_goal_is_one_red_line_under_the_projection(data_dir, hmac_key, tk_mock):
    inputs = ProjectionInputs("31.12.2999", "2", {"Hard": "ten"})

    draw(snapshot_for(data_dir, hmac_key), inputs, tk_mock, progress())

    assert red_lines(tk_mock) == [bad_goal("Hard")]
    assert any(t.startswith("By 31.12.2999") for t in label_texts(tk_mock))


def test_a_goal_without_counts_is_red_too(data_dir, hmac_key, tk_mock):
    inputs = ProjectionInputs("31.12.2999", "2", {"Easy": "100"})

    draw(snapshot_for(data_dir, hmac_key), inputs, tk_mock, None)

    assert red_lines(tk_mock) == [GOAL_NEEDS_COUNTS]


def test_inputs_parse_their_text():
    assert ProjectionInputs("x", " 3 ").price() == 3
    assert ProjectionInputs("x", "0").price() is None
    assert ProjectionInputs("x", "-1").price() is None
    assert ProjectionInputs("x", "").price() is None
    assert ProjectionInputs("x", "2", {"Easy": " ", "Hard": ""}).goal() is None
    goal = ProjectionInputs("x", "2", {"Easy": "837", "Hard": " 1"}).goal()
    assert goal is not None
    assert not isinstance(goal, str)
    assert goal.counts == {"Easy": 837, "Hard": 1}
    assert ProjectionInputs("x", "2", {"Foo": "1"}).goal() == unknown_difficulty("Foo")
    assert ProjectionInputs("x", "2", {"Easy": "1.5"}).goal() == bad_goal("Easy")
