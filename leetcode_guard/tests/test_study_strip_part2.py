"""Tests for what a browser nudge, or a dead doorbell, does to the strip.

The count is the one thing a ring must never move: the browser's word is not
evidence. Only the accent line changes while LeetCode is asked.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from leetcode_guard import _glyphs as g
from leetcode_guard._study_strip import StudyStrip
from leetcode_guard._study_strip_text import StripText
from leetcode_guard.tests.test_study_strip import CONFIG, build


def written(label: MagicMock) -> set[str]:
    return {call.kwargs.get("text") for call in label.configure.call_args_list}


def test_a_ring_changes_the_headline_but_never_the_count():
    text = StripText(elapsed_seconds=61.0, needed=2, verifying=True)

    assert text.headline == f"{g.SOLVED} …"
    assert text.owed == g.OWED * 2


def test_without_a_ring_the_headline_is_the_elapsed_time():
    assert StripText(elapsed_seconds=61.0, needed=2).headline == "01:01"


def test_a_dead_doorbell_is_admitted_in_the_title():
    assert StripText(0, 1, fast_path_down=True).title == f"{g.WATCHING} {g.NO_ENTRY}"
    assert StripText(0, 1).title == g.WATCHING


def test_the_tick_rewrites_the_title(tk_mock):
    strip = build()

    strip.tick(StripText(elapsed_seconds=0, needed=1, fast_path_down=True))

    assert f"{g.WATCHING} {g.NO_ENTRY}" in written(strip._title.label)
    colours = {c.kwargs.get("fg") for c in strip._title.label.configure.call_args_list}
    assert CONFIG.palette.warning in colours
    assert tk_mock.Label.call_count >= 1


def test_a_strip_without_a_title_label_still_ticks():
    elapsed, needed = MagicMock(), MagicMock()
    strip = StudyStrip(MagicMock(), elapsed, needed)

    strip.tick(StripText(elapsed_seconds=0, needed=1, verifying=True))

    assert written(elapsed) == {f"{g.SOLVED} …"}
    assert written(needed) == {g.OWED}
