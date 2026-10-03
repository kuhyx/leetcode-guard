"""Render the suggestion list on a lock surface.

Split out of ``_view.py`` for the 250-line cap. It is the one part of the
surface with real structure -- a row per problem, each with a button -- so it
carries most of the painting code while ``_view.py`` keeps the layout.

Same rules as its parent: pure painting, no I/O, and ``on_fill`` for text on an
accent fill.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING, Any, Final

from leetcode_guard._constants import PROBLEM_DISPLAY_LIMIT

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import LockConfig

    from leetcode_guard._viewmodel import ProblemLine, ViewModel

_PAD = 16

INITIAL_ROWS: Final = 2 * PROBLEM_DISPLAY_LIMIT
"""Rows built up front: the visible eight plus one batch to scroll into."""

ROW_BATCH: Final = PROBLEM_DISPLAY_LIMIT
"""Rows added each time the list is scrolled near its end."""

NO_PROBLEMS_TEXT = "Solve any LeetCode problem -- any accepted submission counts."
"""Shown when there is nothing to suggest.

Shared with ``_view_update`` because the list can also empty out *while* the
lock is up, once enough of it has been solved: the row widgets stay, so the
repaint has to be able to put this sentence back into one of them.
"""


def build_problem_rows(
    parent: tk.Misc,
    config: LockConfig,
    model: ViewModel,
    on_open: Callable[[str], None] | None,
    *,
    bind: Callable[[Any], None] | None = None,
) -> tuple[list[Any], list[Any]]:
    """Render the first rows of the suggestion list, or a stand-in.

    Each problem is one row: its title on the left, a button that opens it on
    the right. The raw URL is deliberately *not* printed any more -- it was only
    ever there because there was nothing to click, and dropping that second line
    is what buys the vertical room the break-glass block needs.

    Only :data:`INITIAL_ROWS` are built; the rest arrive through
    :func:`append_rows` as the list is scrolled (``_view_scroll``).

    Returns:
        The label widgets and the Open buttons, in list order.
    """
    if not model.problems:
        placeholder = tk.Label(
            parent,
            text=NO_PROBLEMS_TEXT,
            font=config.font("body"),
            fg=config.palette.fg,
            bg=config.palette.field_bg,
            anchor="w",
        )
        placeholder.pack(fill="x", padx=_PAD, pady=_PAD // 2)
        return [placeholder], []
    return append_rows(
        parent, config, model.problems[:INITIAL_ROWS], on_open, bind=bind
    )


def append_rows(
    parent: tk.Misc,
    config: LockConfig,
    lines: tuple[ProblemLine, ...],
    on_open: Callable[[str], None] | None,
    *,
    bind: Callable[[Any], None] | None = None,
) -> tuple[list[Any], list[Any]]:
    """Build one row per line under ``parent``.

    Args:
        parent: The scrolling frame the rows stack in.
        config: Fonts and palette.
        lines: What the new rows show.
        on_open: The Open handler, or ``None`` for a list without buttons.
        bind: Called on every new widget, so the wheel scrolls over it.

    Returns:
        The new labels and buttons, in list order.
    """
    labels: list[Any] = []
    buttons: list[Any] = []
    for line in lines:
        row = tk.Frame(parent, bg=config.palette.field_bg)
        row.pack(fill="x", padx=_PAD, pady=_PAD // 4)
        label = tk.Label(
            row,
            text=line.label,
            font=config.font("body"),
            fg=config.palette.fg,
            bg=config.palette.field_bg,
            anchor="w",
            justify="left",
        )
        label.pack(side="left", fill="x", expand=True)
        labels.append(label)
        widgets: list[Any] = [row, label]
        if on_open is not None:
            button = tk.Button(
                row,
                text="Open",
                font=config.font("body"),
                # on_fill on an accent fill, per the module note.
                fg=config.palette.on_fill,
                bg=config.palette.accent,
                # The default argument is load-bearing: a bare closure over
                # `line` would capture the loop variable, so every button would
                # open whichever problem happened to be last.
                command=lambda url=line.url: on_open(url),
                relief="flat",
            )
            button.pack(side="right", padx=_PAD // 2)
            buttons.append(button)
            widgets.append(button)
        if bind is not None:
            for widget in widgets:
                bind(widget)
    return labels, buttons
