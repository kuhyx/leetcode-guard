"""Phase 2's ``?`` button: each SOLVE row opens the tutor's rework chat.

kuhy, 2026-11-22: the chat adds cards to the unit's FIRST mapped module, so the
route names it: ``/rework/<subject>/<module>/<slug>``. The button lives in the
slot ``_view_problems`` reserved for it and shows on SOLVE only; on any other
screen it keeps the slot, blank and inert.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from leetcode_guard import _glyphs as g
from leetcode_guard._phase import PhaseState
from leetcode_guard._unit_view import _assemble
from leetcode_guard._view_problems import append_rows
from leetcode_guard._view_types import ProblemList, RowWiring, ViewHooks
from leetcode_guard._view_update import apply_viewmodel
from leetcode_guard._viewmodel_lines import ProblemLine
from leetcode_guard._viewmodel_phase import build_phase_screen, rework_route
from leetcode_guard.tests._phase_fixtures import SOLVE, SUBJECT, THEORY, unit_pool
from leetcode_guard.tests._view_fixtures import mock_view, model
from leetcode_guard.tests.test_lock_learn import _no_tutor_spawn  # fixture
from leetcode_guard.tests.test_lock_study import locked_guard

if TYPE_CHECKING:
    from pathlib import Path

REWORKABLE = replace(SOLVE, rework_target=(SUBJECT, "prefix-sums"))
LINES = (
    ProblemLine(label="1  range-sum", url="https://x/range-sum/", slug="range-sum"),
    ProblemLine(label="2  pivot", url="https://x/pivot-index/", slug="pivot-index"),
)
__all__ = ["_no_tutor_spawn"]


def test_solve_names_the_units_first_module_and_theory_names_none():
    """The target is the unit's first mapped module, SOLVE only."""
    state = PhaseState(
        unit="u", phase="solve", subject=SUBJECT, modules=("first", "second")
    )
    assert _assemble(state, minutes=0, done={}, cards=None).rework_target == (
        SUBJECT,
        "first",
    )
    theory = replace(state, phase="theory")
    assert _assemble(theory, minutes=0, done={}, cards=None).rework_target is None


def test_the_route_carries_subject_module_and_slug():
    """One path the tutor parses; the screen holds the target, rows the slug."""
    assert build_phase_screen(REWORKABLE).rework == (SUBJECT, "prefix-sums")
    assert build_phase_screen(THEORY).rework is None
    assert rework_route((SUBJECT, "prefix-sums"), "range-sum") == (
        f"/rework/{SUBJECT}/prefix-sums/range-sum"
    )


def test_a_live_row_builds_a_rework_button_bound_to_its_slug(tk_mock: MagicMock):
    """The reserved slot becomes the ``?`` button, rightmost, with a tooltip."""
    pressed: list[str] = []
    wiring = RowWiring(on_rework=pressed.append, rework_live=True)

    append_rows(MagicMock(), MagicMock(), LINES, lambda _url: None, wiring)

    rework = [
        call.kwargs
        for call in tk_mock.Button.call_args_list
        if call.kwargs.get("text") == g.REWORK
    ]
    assert len(rework) == len(LINES) == len(wiring.rework)
    rework[1]["command"]()
    assert pressed == ["pivot-index"]


def test_an_unwired_list_keeps_the_blank_slot(tk_mock: MagicMock):
    """No handler (the fit harness, read-only renders): no ``?`` at all."""
    append_rows(MagicMock(), MagicMock(), LINES, None, RowWiring())

    texts = [call.kwargs.get("text") for call in tk_mock.Button.call_args_list]
    assert g.REWORK not in texts


def _view_with_rework(count: int, pressed: list[str]):
    labels = [MagicMock(name=f"label{i}") for i in range(count)]
    return mock_view(
        problems=ProblemList(
            labels=labels,
            buttons=[MagicMock(name=f"open{i}") for i in range(count)],
            rework=[MagicMock(name=f"rework{i}") for i in range(count)],
            shown=count,
        ),
        hooks=ViewHooks(on_open=lambda _u: None, on_rework=pressed.append),
    )


def test_a_repaint_shows_the_button_on_solve_and_rebinds_it():
    """A solve promotes the next problem; ``?`` follows it, like Open."""
    pressed: list[str] = []
    view = _view_with_rework(2, pressed)

    apply_viewmodel(
        [view], model(problems=LINES, screen=build_phase_screen(REWORKABLE))
    )

    last = view.problems.rework[1].configure.call_args.kwargs
    assert (last["text"], last["state"]) == (g.REWORK, "normal")
    last["command"]()
    assert pressed == ["pivot-index"]
    assert view.problems.rework_live


def test_a_repaint_blanks_the_button_off_solve():
    """THEORY: the slot stays, empty and inert; THEORY's own button teaches."""
    view = _view_with_rework(2, [])

    apply_viewmodel([view], model(problems=LINES, screen=build_phase_screen(THEORY)))

    last = view.problems.rework[0].configure.call_args.kwargs
    assert (last["text"], last["state"]) == ("", "disabled")
    assert not view.problems.rework_live


def test_the_lock_opens_the_rework_route_in_study_mode(
    tmp_path: Path, hmac_key: Path, no_tutor_spawn: list[str]
):
    """Same path as learn: grab down, tutor on ``/rework/...``, strip up."""
    guard = locked_guard(tmp_path, hmac_key, pool=unit_pool(), phase=lambda: REWORKABLE)

    guard.open_rework("range-sum")

    assert no_tutor_spawn == [f"/rework/{SUBJECT}/prefix-sums/range-sum"]
    assert guard.session().active


def test_no_target_opens_nothing(
    tmp_path: Path, hmac_key: Path, no_tutor_spawn: list[str]
):
    """A stale press after the screen left SOLVE is ignored, the grab kept."""
    guard = locked_guard(tmp_path, hmac_key, pool=unit_pool(), phase=lambda: THEORY)

    guard.open_rework("range-sum")

    assert no_tutor_spawn == []
    guard.lock.root.grab_release.assert_not_called()
