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

from leetcode_guard import _glyphs as g
from leetcode_guard._constants import PROBLEM_DISPLAY_LIMIT
from leetcode_guard._view_types import RowWiring

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import LockConfig

    from leetcode_guard._viewmodel import ProblemLine, ViewModel

_PAD = 16

INITIAL_ROWS: Final = 2 * PROBLEM_DISPLAY_LIMIT
"""Rows built up front: the visible eight plus one batch to scroll into."""

ROW_BATCH: Final = PROBLEM_DISPLAY_LIMIT
"""Rows added each time the list is scrolled near its end."""

NO_PROBLEMS_TEXT = f"{g.ANY}  {g.CREDIT}"
"""Shown when there is nothing to suggest: any accepted submission earns.

Shared with ``_view_update`` because the list can also empty out *while* the
lock is up, once enough of it has been solved: the row widgets stay, so the
repaint has to be able to put this sentence back into one of them.
"""


def mark_colour(config: LockConfig, difficulty: str) -> str:
    """The weight mark's second channel: green, amber, red by difficulty."""
    palette = config.palette
    return {
        "Easy": palette.success,
        "Medium": palette.warning,
        "Hard": palette.danger,
    }.get(difficulty, palette.muted)


def build_problem_rows(
    parent: tk.Misc,
    config: LockConfig,
    model: ViewModel,
    on_open: Callable[[str], None] | None,
    wiring: RowWiring | None = None,
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
    return append_rows(parent, config, model.problems[:INITIAL_ROWS], on_open, wiring)


def append_rows(
    parent: tk.Misc,
    config: LockConfig,
    lines: tuple[ProblemLine, ...],
    on_open: Callable[[str], None] | None,
    wiring: RowWiring | None = None,
) -> tuple[list[Any], list[Any]]:
    """Build one row per line under ``parent``.

    Args:
        parent: The scrolling frame the rows stack in.
        config: Fonts and palette.
        lines: What the new rows show.
        on_open: The Open handler, or ``None`` for a list without buttons.
        wiring: The wheel binding and the mark sink; ``None`` for neither.

    Returns:
        The new labels and buttons, in list order.
    """
    wiring = wiring if wiring is not None else RowWiring()
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
        mark = tk.Label(
            row,
            text=line.mark,
            font=config.font("body"),
            fg=mark_colour(config, line.difficulty),
            bg=config.palette.field_bg,
        )
        mark.pack(side="left", padx=_PAD // 2)
        wiring.marks.append(mark)
        widgets: list[Any] = [row, label, mark]
        if on_open is not None:
            button = tk.Button(
                row,
                text=g.OPEN,
                width=3,
                font=config.font("subtitle", bold=True),
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
        if wiring.bind is not None:
            for widget in widgets:
                wiring.bind(widget)
    return labels, buttons
