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
    """Collect every text a mocked label was configured with."""
    return {call.kwargs.get("text") for call in label.configure.call_args_list}


def test_a_ring_changes_the_headline_but_never_the_count():
    """A verifying ring swaps the headline but leaves the owed count as is."""
    text = StripText(elapsed_seconds=61.0, needed=2, verifying=True)

    assert text.headline == f"{g.SOLVED} …"
    assert text.owed == g.OWED * 2


def test_without_a_ring_the_headline_is_the_elapsed_time():
    """With no ring pending, the headline shows the elapsed study time."""
    assert StripText(elapsed_seconds=61.0, needed=2).headline == "01:01"


def test_a_dead_doorbell_is_admitted_in_the_title():
    """A down fast path is admitted in the title; otherwise the title is the default."""
    assert StripText(0, 1, fast_path_down=True).title == f"{g.WATCHING} {g.NO_ENTRY}"
    assert StripText(0, 1).title == g.WATCHING


def test_the_tick_rewrites_the_title(tk_mock):
    """A tick rewrites the title label built by build_strip with the new title."""
    labels = [MagicMock() for _ in range(10)]
    tk_mock.Label.side_effect = labels
    strip = build()
    made = tk_mock.Label.call_args_list
    title_label = next(
        label
        for call, label in zip(made, labels[: len(made)], strict=True)
        if call.kwargs.get("text") == StripText(0, 1).title
    )

    strip.tick(StripText(elapsed_seconds=0, needed=1, fast_path_down=True))

    assert f"{g.WATCHING} {g.NO_ENTRY}" in written(title_label)
    colours = {c.kwargs.get("fg") for c in title_label.configure.call_args_list}
    assert CONFIG.palette.warning in colours
    assert tk_mock.Label.call_count >= 1


def test_a_strip_without_a_title_label_still_ticks():
    """A strip built with no title label still updates elapsed and needed labels."""
    elapsed, needed = MagicMock(), MagicMock()
    strip = StudyStrip(MagicMock(), elapsed, needed)

    strip.tick(StripText(elapsed_seconds=0, needed=1, verifying=True))

    assert written(elapsed) == {f"{g.SOLVED} …"}
    assert written(needed) == {g.OWED}
