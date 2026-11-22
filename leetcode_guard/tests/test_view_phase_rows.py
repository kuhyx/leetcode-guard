"""A unit hand-over swaps the whole list: rows come back, never rebuilt."""

from __future__ import annotations

from unittest.mock import MagicMock

from leetcode_guard._constants import PROBLEM_DISPLAY_LIMIT
from leetcode_guard._view_types import ProblemList, ViewHooks
from leetcode_guard._view_update import apply_viewmodel
from leetcode_guard._viewmodel_lines import ProblemLine
from leetcode_guard._viewmodel_phase import PHASE_ROWS, build_phase_screen
from leetcode_guard.tests._phase_fixtures import NEXT, THEORY
from leetcode_guard.tests._view_fixtures import mock_view, model


def _lines(*slugs: str) -> tuple[ProblemLine, ...]:
    return tuple(
        ProblemLine(label=f"{n}  {s}", url=f"https://x/{s}/", slug=s)
        for n, s in enumerate(slugs, start=1)
    )


def _rows_view(count: int, *, rows: int = PROBLEM_DISPLAY_LIMIT):
    """A surface with ``count`` built rows, each row frame its own mock."""
    labels = [MagicMock(name=f"label{i}") for i in range(count)]
    for label in labels:
        label.master = MagicMock(name="row")
    return mock_view(
        problems=ProblemList(
            labels=labels,
            buttons=[MagicMock(name=f"open{i}") for i in range(count)],
            marks=[MagicMock(name=f"mark{i}") for i in range(count)],
            scroll=MagicMock(),
            shown=count,
            fitted=(rows, min(count, rows)),
        ),
        hooks=ViewHooks(on_open=lambda _u: None),
    )


def test_rows_hidden_by_solves_come_back_for_the_next_unit():
    """SOLVE(u) with one row left, then THEORY(next) with three: re-packed."""
    view = _rows_view(4)
    apply_viewmodel([view], model(problems=_lines("a")))
    hidden = [label.master for label in view.problems.labels[1:]]
    assert all(row.pack_forget.called for row in hidden)
    assert view.problems.shown == 1

    apply_viewmodel([view], model(problems=_lines("b", "c", "d")))

    assert [row.pack.called for row in hidden] == [True, True, False]
    assert view.problems.shown == 3
    view.problems.labels[2].configure.assert_called_with(text="3  d")


def test_a_longer_next_unit_builds_rows_at_the_tail(tk_mock):
    """More problems than built rows: the next batch is built, not rebuilt."""
    view = _rows_view(2)
    before = list(view.problems.labels)

    apply_viewmodel([view], model(problems=_lines(*"abcdefg")))

    assert view.problems.labels[:2] == before
    assert len(view.problems.labels) == 7
    assert view.problems.shown == 7
    assert tk_mock.Button.call_count == 5


def test_the_viewport_refits_when_the_screen_height_changes():
    """none (8 rows) -> THEORY (5 rows): fitted once, then left alone."""
    view = _rows_view(6)
    theory = model(problems=_lines(*"abcdef"), screen=build_phase_screen(THEORY))

    apply_viewmodel([view], theory)
    apply_viewmodel([view], theory)

    view.problems.scroll.fit_rows.assert_called_once_with(6, PHASE_ROWS)
    assert view.problems.fitted == (PHASE_ROWS, PHASE_ROWS)


def test_a_solve_never_shrinks_the_viewport_but_returning_rows_grow_it():
    """A hidden row leaves its gap; a unit with more rows refits."""
    view = _rows_view(3, rows=PHASE_ROWS)
    screen = build_phase_screen(THEORY)
    apply_viewmodel([view], model(problems=_lines("a"), screen=screen))
    view.problems.scroll.fit_rows.assert_not_called()

    apply_viewmodel(
        [view], model(problems=_lines(*"bcd"), screen=build_phase_screen(NEXT))
    )

    view.problems.scroll.fit_rows.assert_not_called()
    assert view.problems.shown == 3
    view.problems.fitted = (PHASE_ROWS, 1)
    apply_viewmodel([view], model(problems=_lines(*"bcd"), screen=screen))
    view.problems.scroll.fit_rows.assert_called_once_with(3, PHASE_ROWS)


def test_hand_made_views_without_row_tracking_are_left_as_they_were():
    """``shown`` None: no re-pack, no refit -- the old behaviour exactly."""
    view = mock_view(
        problems=ProblemList(labels=[MagicMock()], scroll=MagicMock(), shown=None)
    )

    apply_viewmodel([view], model(problems=_lines("a", "b")))

    view.problems.labels[0].master.pack.assert_not_called()
    view.problems.scroll.fit_rows.assert_not_called()
