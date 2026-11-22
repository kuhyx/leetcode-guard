"""Tests for what a browser nudge, or a dead doorbell, does to the strip.

The count is the one thing a ring must never move: the browser's word is not
evidence. Only the accent line changes while LeetCode is asked, and that line
is absent (no empty gap) when nothing is being asked.
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


def build_with_labels(
    tk_mock: MagicMock, text: StripText | None = None
) -> tuple[StudyStrip, MagicMock, MagicMock]:
    """A strip over a distinct title label and headline label."""
    title, headline = MagicMock(), MagicMock()
    tk_mock.Label.side_effect = [title, headline]
    return build(text=text), title, headline


def test_a_ring_changes_the_headline_but_never_the_count():
    """A verifying ring swaps the headline but leaves the dot counts as is."""
    text = StripText(needed=2, earned=1, verifying=True)

    assert text.headline == f"{g.SOLVED} …"
    assert (text.filled, text.hollow) == (1, 2)


def test_a_dead_doorbell_is_admitted_in_the_title():
    """A down fast path is admitted in the title; otherwise the title is the default."""
    assert StripText(1, fast_path_down=True).title == f"{g.WATCHING} {g.NO_ENTRY}"
    assert StripText(1).title == g.WATCHING


def test_the_tick_rewrites_the_title(tk_mock):
    """A tick rewrites the title label built by build_strip with the new title."""
    strip, title, _headline = build_with_labels(tk_mock)

    strip.tick(StripText(needed=1, fast_path_down=True))

    assert f"{g.WATCHING} {g.NO_ENTRY}" in written(title)
    colours = {c.kwargs.get("fg") for c in title.configure.call_args_list}
    assert CONFIG.palette.warning in colours


def test_a_strip_without_a_title_label_still_ticks():
    """A strip built with no title label still repaints its dots."""
    dots = MagicMock()
    strip = StudyStrip(MagicMock(), MagicMock(), dots)

    strip.tick(StripText(needed=2, earned=1))

    dots.paint.assert_called_once_with(1, 2)


def test_the_headline_is_absent_while_nothing_is_verified(tk_mock):
    """Never packed, so the strip has no empty line."""
    _strip, _title, headline = build_with_labels(tk_mock)

    headline.pack.assert_not_called()


def test_the_headline_appears_and_goes_with_the_verdict_check(tk_mock):
    """Shown once while verifying, removed once when it ends, never repacked."""
    strip, _title, headline = build_with_labels(tk_mock)

    strip.tick(StripText(needed=1, verifying=True))
    strip.tick(StripText(needed=1, verifying=True))
    assert written(headline) == {f"{g.SOLVED} …"}
    headline.pack.assert_called_once()
    headline.pack_forget.assert_not_called()

    strip.tick(StripText(needed=1))
    strip.tick(StripText(needed=1))
    headline.pack_forget.assert_called_once()


def test_a_strip_built_while_verifying_shows_the_headline_at_once(tk_mock):
    """The first paint is never behind the text it was handed."""
    _strip, _title, headline = build_with_labels(
        tk_mock, StripText(needed=1, verifying=True)
    )

    headline.pack.assert_called_once()
    assert tk_mock.Label.call_args_list[1].kwargs["text"] == f"{g.SOLVED} …"


def fills(canvas: MagicMock) -> list[str]:
    """The fill of every dot drawn, in order; empty string is hollow."""
    return [c.kwargs["fill"] for c in canvas.create_oval.call_args_list]


def test_earned_dots_are_filled_and_owed_dots_are_hollow(tk_mock):
    """One filled dot for the credit earned, six hollow for the six owed."""
    build(text=StripText(needed=6, earned=1))

    drawn = fills(tk_mock.Canvas.return_value)
    assert drawn == [CONFIG.palette.success] + [""] * 6


def test_the_dots_repaint_only_when_a_count_moves(tk_mock):
    """The 1 s tick re-lifts; it does not redraw an unchanged row."""
    strip = build(text=StripText(needed=2, earned=1))
    canvas = tk_mock.Canvas.return_value
    canvas.reset_mock()

    strip.tick(StripText(needed=2, earned=1))
    canvas.create_oval.assert_not_called()
    strip.tick(StripText(needed=1, earned=2))
    assert fills(canvas) == [CONFIG.palette.success] * 2 + [""]
    canvas.delete.assert_called_once_with("all")


def test_a_wrapped_row_grows_the_canvas_instead_of_clipping(tk_mock):
    """Every one of 28 dots is drawn and the canvas is as tall as the rows."""
    strip = build(text=StripText(needed=20, earned=8))
    canvas = tk_mock.Canvas.return_value

    assert canvas.create_oval.call_count == 28
    first = canvas.create_oval.call_args_list[0].args
    assert first[2] - first[0] == first[3] - first[1] >= 16
    assert canvas.configure.call_args.kwargs["height"] > 40
    strip.tick(StripText(needed=7))
    assert canvas.create_oval.call_count == 35


def test_nothing_owed_draws_the_check_not_dots(tk_mock):
    """Fully paid keeps today's check."""
    build(text=StripText(needed=0, earned=3))
    canvas = tk_mock.Canvas.return_value

    canvas.create_oval.assert_not_called()
    assert canvas.create_text.call_args.kwargs["text"] == g.SOLVED
