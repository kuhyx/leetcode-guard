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

Rows only ever empty out, never grow: the solved set grows monotonically and
the pool is fixed for the life of the window. So surplus rows are hidden from
the tail and never need re-showing in the middle of the list.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._view_problems import NO_PROBLEMS_TEXT

if TYPE_CHECKING:
    from collections.abc import Iterable

    from leetcode_guard._view import GuardView
    from leetcode_guard._viewmodel import ProblemLine, ViewModel


def apply_viewmodel(views: Iterable[GuardView], model: ViewModel) -> int:
    """Push ``model`` onto each surface.

    Returns:
        How many surfaces were updated.
    """
    count = 0
    for view in views:
        view.headline.configure(text=model.headline)
        view.balance_line.configure(text=model.balance_line)
        view.status_line.configure(text=model.status_line)
        view.notes_label.configure(text="\n".join(model.notes))
        _apply_problem_rows(view, model.problems)
        _apply_escape_visibility(view, model)
        count += 1
    return count


def _apply_problem_rows(view: GuardView, lines: tuple[ProblemLine, ...]) -> None:
    """Re-point the existing rows at the problems still worth solving."""
    labels = view.problem_labels
    if not labels:
        return
    if not lines:
        # Everything on offer has been solved. The first widget carries the
        # stand-in sentence -- which is where it already is when the list was
        # empty from the start, so this branch handles both.
        labels[0].configure(text=NO_PROBLEMS_TEXT)
        _hide_open_button(view, 0)
        _hide_rows_from(view, 1)
        return
    visible = lines[: len(labels)]
    for index, line in enumerate(visible):
        labels[index].configure(text=line.label)
        _rebind_open_button(view, index, line.url)
    _hide_rows_from(view, len(visible))


def _rebind_open_button(view: GuardView, index: int, url: str) -> None:
    """Point one row's Open button at whatever that row now shows."""
    if index >= len(view.open_buttons):
        return
    handler = view.on_open
    if handler is None:
        return
    # Same default-argument trick as the builder: a bare closure would capture
    # the loop variable and every button would open the last problem.
    view.open_buttons[index].configure(command=lambda target=url: handler(target))


def _hide_open_button(view: GuardView, index: int) -> None:
    """Take one Open button off the screen without destroying it."""
    if index < len(view.open_buttons):
        view.open_buttons[index].pack_forget()


def _hide_rows_from(view: GuardView, start: int) -> None:
    """Hide the tail of the list, row frame and button together."""
    for label in view.problem_labels[start:]:
        label.master.pack_forget()


def _apply_escape_visibility(view: GuardView, model: ViewModel) -> None:
    """Show or hide the escape button without rebuilding it."""
    if view.escape_button is None:
        return
    if model.show_escape:
        view.escape_button.pack(pady=(16, 0))
    else:
        view.escape_button.pack_forget()
