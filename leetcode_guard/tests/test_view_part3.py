"""Tests for repainting the suggestion list in place.

The rest of ``apply_viewmodel`` is in ``test_view_part2.py``; this is the half
that moves rows. Tk is a MagicMock throughout, so these assert on what was
asked of the widgets -- which is the whole point here, since the invariant
under test is that nothing is ever *destroyed*.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from leetcode_guard._view import GuardView
from leetcode_guard._view_problems import NO_PROBLEMS_TEXT
from leetcode_guard._view_update import apply_viewmodel
from leetcode_guard._viewmodel import ProblemLine, ViewModel


def model(*lines: ProblemLine) -> ViewModel:
    return ViewModel(
        headline="Solve 2 LeetCode problems to unlock",
        balance_line="Credits 0  |  Monday costs 2",
        status_line="Watching...",
        notes=(),
        problems=lines,
        unlocked=False,
        show_escape=False,
    )


def rows_view(count: int, *, buttons: int | None = None, on_open=None) -> GuardView:
    """A surface whose list was built with ``count`` rows."""
    return GuardView(
        output_name="DP-0",
        container=MagicMock(),
        headline=MagicMock(),
        balance_line=MagicMock(),
        status_line=MagicMock(),
        notes_label=MagicMock(),
        problem_labels=[MagicMock() for _ in range(count)],
        problems_frame=MagicMock(),
        open_buttons=[
            MagicMock() for _ in range(count if buttons is None else buttons)
        ],
        on_open=on_open,
    )


def test_a_solved_problem_frees_its_slot_and_the_bench_moves_up():
    """The reported bug, at the widget layer.

    Row 1 showed the problem that was just accepted. After the repaint it
    shows the next one, and the list is one row shorter -- not one row of
    dead text plus a gap.
    """
    view = rows_view(3, on_open=MagicMock())

    apply_viewmodel(
        [view],
        model(
            ProblemLine(label="1. B", url="https://x/b/"),
            ProblemLine(label="2. C", url="https://x/c/"),
        ),
    )

    view.problem_labels[0].configure.assert_called_once_with(text="1. B")
    view.problem_labels[1].configure.assert_called_once_with(text="2. C")
    view.problem_labels[2].master.pack_forget.assert_called_once_with()


def test_a_promoted_row_opens_the_problem_it_now_shows():
    """A row that is re-pointed must have its Open button re-pointed too.

    The button's command closes over the URL it was *built* with, so without
    the rebind the top row would open the problem that was just solved --
    which is the same bug wearing the fix as a disguise.
    """
    handler = MagicMock()
    view = rows_view(2, on_open=handler)

    apply_viewmodel([view], model(ProblemLine(label="1. B", url="https://x/b/")))

    command = view.open_buttons[0].configure.call_args.kwargs["command"]
    command()
    handler.assert_called_once_with("https://x/b/")


def test_no_row_is_ever_destroyed():
    """The 2026-08-05 rule: never a moment with no Open button on screen.

    A destroy-and-rebuild repaint satisfies every text assertion above and
    still opens that window, so the absence of ``destroy`` is asserted
    directly.
    """
    view = rows_view(2, on_open=MagicMock())

    apply_viewmodel([view], model(ProblemLine(label="1. B", url="https://x/b/")))

    for label in view.problem_labels:
        label.destroy.assert_not_called()
    for button in view.open_buttons:
        button.destroy.assert_not_called()
    view.problems_frame.destroy.assert_not_called()


def test_solving_everything_on_offer_leaves_the_stand_in_sentence():
    """An empty list must still say what counts, not show a blank panel."""
    view = rows_view(2, on_open=MagicMock())

    apply_viewmodel([view], model())

    view.problem_labels[0].configure.assert_called_once_with(text=NO_PROBLEMS_TEXT)
    view.open_buttons[0].pack_forget.assert_called_once_with()
    view.problem_labels[1].master.pack_forget.assert_called_once_with()


def test_an_inert_list_is_repainted_without_rebinding_anything():
    """``on_open`` is ``None`` for read-only renders; the text still updates."""
    view = rows_view(1, on_open=None)

    apply_viewmodel([view], model(ProblemLine(label="1. B", url="https://x/b/")))

    view.problem_labels[0].configure.assert_called_once_with(text="1. B")
    view.open_buttons[0].configure.assert_not_called()


def test_a_row_without_a_button_is_repainted_anyway():
    """The placeholder path builds one label and no buttons at all."""
    view = rows_view(1, buttons=0, on_open=MagicMock())

    apply_viewmodel([view], model(ProblemLine(label="1. B", url="https://x/b/")))

    view.problem_labels[0].configure.assert_called_once_with(text="1. B")


def test_an_empty_list_with_no_buttons_still_gets_the_stand_in():
    view = rows_view(1, buttons=0, on_open=MagicMock())

    apply_viewmodel([view], model())

    view.problem_labels[0].configure.assert_called_once_with(text=NO_PROBLEMS_TEXT)
