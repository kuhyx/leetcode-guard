"""Review first (kuhy, 2026-11-22): a due tutor card hides the SOLVE rows.

While at least one card of the current unit's modules is due, SOLVE shows one
REVIEW row and its Open, nothing else of the list. A view rule fed by the
tutor's signed ``review_due.json``: ``decide``, charges and credits never read
it, and "cannot check" shows the SOLVE rows as today (fail open, one warning
per lock run).
"""

from __future__ import annotations

import pytest

from leetcode_guard import _glyphs as g
from leetcode_guard._gate import decide
from leetcode_guard._ledger_io import Ledger
from leetcode_guard._review_due import CLEAR, UNKNOWN
from leetcode_guard._view_types import ViewHooks
from leetcode_guard._view_update import apply_viewmodel
from leetcode_guard._viewmodel import build_viewmodel
from leetcode_guard._viewmodel_phase import build_phase_screen, review_route
from leetcode_guard._viewmodel_source import ViewSource
from leetcode_guard.tests._ledger_fixtures import MONDAY, NOW
from leetcode_guard.tests._phase_fixtures import NONE, PREFIX, THEORY, unit_pool
from leetcode_guard.tests._review_first_fixtures import (
    DUE,
    ROUTE,
    SOLVE_R,
    TARGET,
    slugs_of,
)
from leetcode_guard.tests._view_fixtures import rows_view
from leetcode_guard.tests.test_viewmodel import CHECKED_AT, OK_PROBE, SIGNED_OUT


def _model(phase, review=None, *, solved: frozenset[str] = frozenset()):
    return build_viewmodel(
        decide(Ledger(), day=MONDAY, now=NOW),
        ViewSource(
            unit_pool(),
            SIGNED_OUT,
            limit=99,
            solved_slugs=solved,
            phase=phase,
            review=review,
        ),
        OK_PROBE,
        checked_at=CHECKED_AT,
    )


# -- the view model -------------------------------------------------------


def test_due_cards_show_exactly_one_review_row_and_no_solve_row():
    """Open on the row is the tutor's review route; nothing else of the list."""
    shown = _model(SOLVE_R, DUE)

    assert len(shown.problems) == 1
    line = shown.problems[0]
    assert (line.url, line.slug, line.mark) == (ROUTE, "", "")
    assert line.label == f"{g.REVIEW}  3"
    assert review_route(TARGET) == ROUTE


def test_the_rest_of_the_screen_stays():
    """The unit bar stays; the rework ``?`` goes (it needs a problem row)."""
    shown = _model(SOLVE_R, DUE)

    assert shown.screen.unit_bar == build_phase_screen(SOLVE_R).unit_bar
    assert shown.screen.rework is None
    assert shown.screen.phase == "solve"
    assert shown.needed == _model(SOLVE_R).needed


@pytest.mark.parametrize("review", [None, CLEAR, UNKNOWN])
def test_nothing_due_or_cannot_check_shows_todays_solve_rows(review):
    """Only a known due card replaces the rows: fail open on every other answer."""
    shown = _model(SOLVE_R, review)

    assert slugs_of(shown) == list(PREFIX)
    assert shown.screen == build_phase_screen(SOLVE_R)


@pytest.mark.parametrize("phase", [THEORY, NONE, None])
def test_only_solve_has_a_review_row(phase):
    """THEORY, none and an unknown phase are unchanged by a due card."""
    assert _model(phase, DUE).problems == _model(phase).problems
    assert build_phase_screen(phase, DUE) == build_phase_screen(phase)


def test_a_solve_while_review_shows_is_still_acknowledged():
    """The accepted-submission mark rides the status line, not the rows."""
    shown = _model(SOLVE_R, DUE, solved=frozenset(PREFIX[:1]))

    assert (
        shown.status_line
        == _model(SOLVE_R, None, solved=frozenset(PREFIX[:1])).status_line
    )
    assert shown.status_line != _model(SOLVE_R, DUE).status_line
    assert len(shown.problems) == 1


# -- repainting the open window ------------------------------------------


def test_the_open_window_swaps_in_both_directions_without_a_rebuild():
    """SOLVE -> REVIEW -> SOLVE: rows hidden then back, Open re-bound each time."""
    opened: list[str] = []
    view = rows_view(4)
    view.hooks = ViewHooks(on_open=opened.append)

    apply_viewmodel([view], _model(SOLVE_R))
    assert view.problems.shown == 3
    apply_viewmodel([view], _model(SOLVE_R, DUE))
    assert view.problems.shown == 1
    view.problems.labels[0].configure.assert_called_with(text=f"{g.REVIEW}  3")
    view.problems.buttons[0].configure.call_args.kwargs["command"]()
    assert opened == [ROUTE]
    assert view.problems.marks[0].configure.call_args.kwargs["text"] == ""

    apply_viewmodel([view], _model(SOLVE_R))
    assert view.problems.shown == 3
    view.problems.buttons[0].configure.call_args.kwargs["command"]()
    assert opened[-1] == _model(SOLVE_R).problems[0].url
