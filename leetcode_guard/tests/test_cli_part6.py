"""Continued from :mod:`leetcode_guard.tests.test_cli_part5`: the what-if flags
``--price`` and ``--goal``, which share the window's report code."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard import _cli, _cli_commands
from leetcode_guard._cli_commands import projection_inputs
from leetcode_guard._status_projection import (
    BAD_PRICE,
    GOAL_NEEDS_COUNTS,
    ProjectionInputs,
)
from leetcode_guard.tests.test_projection import progress

if TYPE_CHECKING:
    from pathlib import Path


def test_price_and_goal_print_the_what_if(monkeypatch, capsys, data_dir: Path):
    monkeypatch.setattr(_cli_commands, "fetch_live_progress", progress)

    _cli.main(["--status", "--by", "31.12.2999", "--price", "1", "--goal", "Easy=100"])
    out = capsys.readouterr().out

    assert "Prices: Tue/Wed/Thu cost 1, Mon/Fri/Sat/Sun cost 2." in out
    assert "Goal: Easy 100 (45 more)." in out
    assert "At price 1:" in out
    assert "Price that lands the goal exactly on 31.12.2999:" in out


def test_price_or_goal_alone_implies_the_end_of_year(monkeypatch, capsys, data_dir):
    monkeypatch.setattr(_cli_commands, "fetch_live_progress", progress)

    _cli.main(["--status", "--price", "3"])
    out = capsys.readouterr().out

    assert "by 31.12." in out
    assert "Prices: Tue/Wed/Thu cost 3, Mon/Fri/Sat/Sun cost 6." in out


def test_a_bad_price_is_exit_2(monkeypatch, capsys, data_dir):
    monkeypatch.setattr(_cli_commands, "fetch_live_progress", progress)

    assert _cli.main(["--status", "--price", "0"]) == 2
    assert BAD_PRICE in capsys.readouterr().out


def test_a_bad_goal_is_exit_2_but_the_projection_still_prints(
    monkeypatch, capsys, data_dir
):
    monkeypatch.setattr(_cli_commands, "fetch_live_progress", progress)

    assert _cli.main(["--status", "--goal", "Easy"]) == 2
    out = capsys.readouterr().out

    assert "new problem(s) to solve." in out
    assert "The Easy goal must be a whole number, or blank." in out


def test_a_goal_without_counts_says_what_it_needs(monkeypatch, capsys, data_dir):
    monkeypatch.setattr(_cli_commands, "fetch_live_progress", lambda: None)

    assert _cli.main(["--status", "--goal", "Easy=100"]) == 2
    assert GOAL_NEEDS_COUNTS in capsys.readouterr().out


def test_projection_inputs_mirror_the_flags():
    assert projection_inputs("01.02.2030", 4, ["Easy=1", " Hard = 2 "]) == (
        ProjectionInputs("01.02.2030", "4", {"Easy": "1", "Hard": " 2 "})
    )
    defaults = projection_inputs(None, None, None)
    assert defaults.price_text == "1"
    assert defaults.goal_texts == {}
    assert projection_inputs(None, None, ["Medium"]).goal_texts == {"Medium": "?"}
