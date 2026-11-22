"""Mirror a new view model onto every surface.

Text updates rather than rebuilds. Destroying and recreating the widget tree on
every poll would flicker once a second and would discard anything the user was
part-way through typing in the escape form.

That applies to the suggestion list too, which **is** repainted -- it used not
to be. A lock that demands two solves kept showing the first problem after it
had been accepted, holding a slot that could have named one the user can still
get credit for. The rows are reconfigured in place rather than rebuilt for a
reason that outranks flicker: a destroy/rebuild opens a window, however short,
in which no ``Open`` button exists on screen, and "the lock must always offer a
way to do the thing it demands" is the 2026-08-05 rule.

Rows are only ever *added* at the tail (``_view_scroll.grow_rows``) and never
removed. Within one screen the solved set grows monotonically, so surplus rows
are hidden from the tail. A unit hand-over (SOLVE(u) -> THEORY(next)) swaps the
whole list, so a repaint also re-shows hidden tail rows, in order, and builds
the next batch when the new unit has more problems than rows exist. The THEORY
card and the SOLVE bar are toggled, never rebuilt (``_view_phase``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from gatelock import LockConfig

from leetcode_guard import _glyphs as g
from leetcode_guard._view_phase import paint_phase
from leetcode_guard._view_problems import (
    INITIAL_ROWS,
    NO_PROBLEMS_TEXT,
    mark_colour,
    rework_look,
)
from leetcode_guard._view_scroll import grow_rows

if TYPE_CHECKING:
    from collections.abc import Iterable

    from leetcode_guard._view import GuardView
    from leetcode_guard._viewmodel import ViewModel
    from leetcode_guard._viewmodel_lines import ProblemLine

_DEFAULT_CONFIG: Final = LockConfig()
"""Colours for a view built without one (the tests' hand-made views)."""


def status_colour(config: LockConfig, model: ViewModel) -> str:
    """Muted while watching, danger while LeetCode cannot be checked."""
    return config.palette.muted if model.status_ok else config.palette.danger


def join_notes(notes: tuple[str, ...]) -> str:
    """The warning marks on one line."""
    return g.SEP.join(notes)


def _config_of(view: GuardView) -> LockConfig:
    config = view.decor.config
    return config if isinstance(config, LockConfig) else _DEFAULT_CONFIG


def apply_viewmodel(views: Iterable[GuardView], model: ViewModel) -> int:
    """Push ``model`` onto each surface.

    Returns:
        How many surfaces were updated.
    """
    count = 0
    for view in views:
        if view.decor.padlock is not None:
            view.decor.padlock.draw(locked=not model.unlocked)
        view.headline.configure(text=model.headline)
        view.balance_line.configure(text=model.balance_line)
        view.status_line.configure(
            text=model.status_line, fg=status_colour(_config_of(view), model)
        )
        view.notes_label.configure(text=join_notes(model.notes))
        if view.phase is not None:
            paint_phase(view.phase, _config_of(view), model.screen, view.hooks.on_learn)
        view.problems.lines = model.problems
        _apply_problem_rows(view, model.problems)
        _apply_rework(view, model)
        _refit(view, model.screen.rows)
        _apply_escape_visibility(view, model)
        count += 1
    return count


def _apply_problem_rows(view: GuardView, lines: tuple[ProblemLine, ...]) -> None:
    """Re-point the existing rows at the problems still worth solving."""
    labels = view.problems.labels
    if not labels:
        return
    if not lines:
        # Everything on offer has been solved. The first widget carries the
        # stand-in sentence -- which is where it already is when the list was
        # empty from the start, so this branch handles both.
        labels[0].configure(text=NO_PROBLEMS_TEXT)
        if view.problems.marks:
            view.problems.marks[0].configure(text="")
        _hide_open_button(view, 0)
        _hide_rows_from(view, 1)
        return
    _show_rows(view, len(lines))
    labels = view.problems.labels
    visible = lines[: len(labels)]
    marks = view.problems.marks
    for index, line in enumerate(visible):
        labels[index].configure(text=line.label)
        if index < len(marks):
            marks[index].configure(
                text=line.mark, fg=mark_colour(_config_of(view), line.difficulty)
            )
        _rebind_open_button(view, index, line.url)
    _hide_rows_from(view, len(visible))


def _rebind_open_button(view: GuardView, index: int, url: str) -> None:
    """Point one row's Open button at whatever that row now shows."""
    if index >= len(view.problems.buttons):
        return
    handler = view.hooks.on_open
    if handler is None:
        return
    # Same default-argument trick as the builder: a bare closure would capture
    # the loop variable and every button would open the last problem.
    view.problems.buttons[index].configure(command=lambda target=url: handler(target))


def _apply_rework(view: GuardView, model: ViewModel) -> None:
    """Show ``?`` on SOLVE, blank it elsewhere, and point it at each row's slug."""
    live = model.screen.rework is not None
    view.problems.rework_live = live
    handler = view.hooks.on_rework
    if handler is None:
        return
    slugs = [line.slug for line in model.problems]
    for index, button in enumerate(view.problems.rework):
        slug = slugs[index] if index < len(slugs) else ""
        button.configure(
            **rework_look(live=live and bool(slug)),
            command=lambda target=slug: handler(target),
        )


def _hide_open_button(view: GuardView, index: int) -> None:
    """Take one Open button off the screen without destroying it."""
    if index < len(view.problems.buttons):
        view.problems.buttons[index].pack_forget()


def _hide_rows_from(view: GuardView, start: int) -> None:
    """Hide the tail of the list, row frame and button together."""
    for label in view.problems.labels[start:]:
        label.master.pack_forget()
    if view.problems.shown is not None:
        view.problems.shown = min(view.problems.shown, start)


def _show_rows(view: GuardView, wanted: int) -> None:
    """Re-pack hidden tail rows, then build more, until ``wanted`` show.

    Only a unit hand-over needs this. Hidden rows are re-packed in index
    order, before anything is built, so the packing order stays the list
    order. Building stops at :data:`INITIAL_ROWS`; scrolling builds the rest.
    """
    problems = view.problems
    if problems.shown is None:
        return
    for label in problems.labels[problems.shown : wanted]:
        label.master.pack(fill="x", padx=16, pady=4)
    problems.shown = max(problems.shown, min(wanted, len(problems.labels)))
    if len(problems.labels) < min(wanted, INITIAL_ROWS):
        grow_rows(view, _config_of(view))


def _refit(view: GuardView, rows: int) -> None:
    """Resize the viewport when the screen's height changes or rows came back.

    Never shrinks within a screen: a row hidden by a solve leaves its gap,
    as it always has, so the centred panel does not jump.
    """
    problems = view.problems
    if problems.scroll is None or problems.shown is None:
        return
    shown = min(problems.shown, rows)
    fitted_rows, fitted_shown = problems.fitted
    if rows == fitted_rows and shown <= fitted_shown:
        return
    problems.scroll.fit_rows(problems.shown, rows)
    problems.fitted = (rows, shown)


def _apply_escape_visibility(view: GuardView, model: ViewModel) -> None:
    """Show or hide the escape button without rebuilding it."""
    if view.decor.escape_button is None:
        return
    if model.show_escape:
        view.decor.escape_button.pack(pady=(16, 0))
    else:
        view.decor.escape_button.pack_forget()
