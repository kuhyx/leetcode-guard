"""The end-evening control: one glyph button on every surface, from t=0.

Own module because ``_view.py`` is at the 250-line cap. Pure painting, like the
rest of the view: the press is handed in.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from leetcode_guard import _glyphs as g

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import LockConfig


def install_end_evening_button(
    parent: tk.Misc, config: LockConfig, on_press: Callable[[], None]
) -> tk.Button:
    """The way out of an evening chain, top-right on the **surface**.

    On the surface, not the root, for the reason ``install_demo_close_button``
    gives: the per-output Toplevels sit on top of the root. Top-right keeps it
    clear of the demo close button (top-left). No words: a moon glyph.
    """
    button = tk.Button(
        parent,
        text=g.END_EVENING,
        font=config.font("title"),
        width=2,
        fg=config.palette.on_fill,
        bg=config.palette.accent,
        command=on_press,
        relief="flat",
    )
    button.place(relx=1.0, x=-10, y=10, anchor="ne")
    return button
