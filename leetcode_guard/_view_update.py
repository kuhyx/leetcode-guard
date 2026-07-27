"""Mirror a new view model onto every surface.

Text updates rather than rebuilds. Destroying and recreating the widget tree on
every poll would flicker once a second and would discard anything the user was
part-way through typing in the escape form.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from leetcode_guard._view import GuardView
    from leetcode_guard._viewmodel import ViewModel


def apply_viewmodel(views: Iterable[GuardView], model: ViewModel) -> int:
    """Push ``model`` onto each surface.

    The suggestion list is deliberately *not* re-rendered: it is resolved once
    before the window opens and does not change while the lock is up, so only
    the lines that actually move get touched.

    Returns:
        How many surfaces were updated.
    """
    count = 0
    for view in views:
        view.headline.configure(text=model.headline)
        view.balance_line.configure(text=model.balance_line)
        view.status_line.configure(text=model.status_line)
        view.notes_label.configure(text="\n".join(model.notes))
        _apply_escape_visibility(view, model)
        count += 1
    return count


def _apply_escape_visibility(view: GuardView, model: ViewModel) -> None:
    """Show or hide the escape button without rebuilding it."""
    if view.escape_button is None:
        return
    if model.show_escape:
        view.escape_button.pack(pady=(16, 0))
    else:
        view.escape_button.pack_forget()
