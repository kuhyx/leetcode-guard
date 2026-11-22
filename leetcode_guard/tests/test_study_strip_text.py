"""Tests for the study strip's text: the title, the headline and the dot counts.

The widget half lives in ``test_study_strip.py``, the dot geometry in
``test_strip_dots.py``.
"""

from __future__ import annotations

from dataclasses import fields
import re

from leetcode_guard import _glyphs as g
from leetcode_guard._study_strip_text import StripText


def test_the_strip_carries_no_time_in_any_phase():
    """Time is shown in exactly one place, and it is not the strip."""
    assert "elapsed_seconds" not in {f.name for f in fields(StripText)}
    for text in (
        StripText(needed=3),
        StripText(needed=3, verifying=True),
        StripText(needed=3, fast_path_down=True),
        StripText(needed=0),
    ):
        shown = f"{text.title} {text.headline}"
        assert not re.search(r"\d\d:\d\d", shown)
        assert not hasattr(text, "elapsed")


def test_with_nothing_being_verified_the_headline_is_absent():
    """No headline at all, so the strip leaves no empty line."""
    assert StripText(needed=2).headline == ""


def test_a_verdict_being_checked_shows_the_check():
    """The one thing the headline still says: an Accepted is being verified."""
    assert StripText(needed=2, verifying=True).headline == f"{g.SOLVED} …"


def test_the_dot_counts_are_earned_then_owed():
    """One filled dot per credit earned today, one hollow per credit owed."""
    text = StripText(needed=6, earned=1)

    assert (text.filled, text.hollow) == (1, 6)


def test_an_unreadable_earned_count_draws_no_filled_dot():
    """Cannot read is never an invented dot."""
    text = StripText(needed=6, earned=None)

    assert (text.filled, text.hollow) == (0, 6)


def test_nothing_owed_shows_the_check_alone():
    """All paid: today's behaviour, the solved check and no dots."""
    text = StripText(needed=0, earned=4)

    assert (text.filled, text.hollow) == (0, 0)
    assert text.paid


def test_a_debt_is_not_paid():
    """Anything owed is dots, not the check."""
    assert not StripText(needed=1, earned=9).paid
