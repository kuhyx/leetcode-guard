"""Tests for the study strip's text: what the elapsed and owed lines say.

The widget half lives in ``test_study_strip.py``.
"""

from __future__ import annotations

from leetcode_guard import _glyphs as g
from leetcode_guard._study_strip_text import StripText


def test_the_elapsed_line_counts_up_and_never_down():
    """No deadline exists, so no countdown may be implied. Study mode ends on a
    solve or on the button -- inventing a timer would invent a pressure the
    gate does not actually apply."""
    text = StripText(elapsed_seconds=902.0, needed=1)

    assert text.elapsed == "15:02"
    assert "-" not in text.elapsed


def test_the_elapsed_line_survives_a_clock_that_went_backwards():
    """A negative elapsed time renders as 00:00, never as a minus."""
    assert StripText(elapsed_seconds=-5.0, needed=1).elapsed == "00:00"


def test_the_owed_line_draws_one_circle_per_solve():
    """Each owed solve is one circle on the owed line."""
    assert StripText(elapsed_seconds=0, needed=1).owed == g.OWED
    assert StripText(elapsed_seconds=0, needed=3).owed == g.OWED * 3


def test_nothing_owed_shows_the_check():
    """With nothing owed, the owed line shows the solved check."""
    assert StripText(elapsed_seconds=0, needed=0).owed == g.SOLVED
