"""Render the suggestion list on a lock surface.

Split out of ``_view.py`` for the 250-line cap. It is the one part of the
surface with real structure -- a row per problem, each with a button -- so it
carries most of the painting code while ``_view.py`` keeps the layout.

Same rules as its parent: pure painting, no I/O, and ``on_fill`` for text on an
accent fill.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import LockConfig

    from leetcode_guard._viewmodel import ViewModel

_PAD = 16


def build_problem_rows(
    parent: tk.Misc,
    config: LockConfig,
    model: ViewModel,
    on_open: Callable[[str], None] | None,
) -> tuple[list[Any], list[Any]]:
    """Render the suggestion list, or a stand-in when there isn't one.

    Each problem is one row: its title on the left, a button that opens it on
    the right. The raw URL is deliberately *not* printed any more -- it was only
    ever there because there was nothing to click, and dropping that second line
    is what buys the vertical room the break-glass block needs.

    Returns:
        The label widgets and the Open buttons, in list order.
    """
    if not model.problems:
        placeholder = tk.Label(
            parent,
            text="Solve any LeetCode problem -- any accepted submission counts.",
            font=config.font("body"),
            fg=config.fg,
            bg=config.field_bg,
            anchor="w",
        )
        placeholder.pack(fill="x", padx=_PAD, pady=_PAD // 2)
        return [placeholder], []

    labels: list[Any] = []
    buttons: list[Any] = []
    for line in model.problems:
        row = tk.Frame(parent, bg=config.field_bg)
        row.pack(fill="x", padx=_PAD, pady=_PAD // 4)
        label = tk.Label(
            row,
            text=line.label,
            font=config.font("body"),
            fg=config.fg,
            bg=config.field_bg,
            anchor="w",
            justify="left",
        )
        label.pack(side="left", fill="x", expand=True)
        labels.append(label)
        if on_open is not None:
            button = tk.Button(
                row,
                text="Open",
                font=config.font("body"),
                # on_fill on an accent fill, per the module note.
                fg=config.on_fill,
                bg=config.accent,
                # The default argument is load-bearing: a bare closure over
                # `line` would capture the loop variable, so every button would
                # open whichever problem happened to be last.
                command=lambda url=line.url: on_open(url),
                relief="flat",
            )
            button.pack(side="right", padx=_PAD // 2)
            buttons.append(button)
    return labels, buttons
