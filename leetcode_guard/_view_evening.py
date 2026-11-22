"""The surface buttons placed in a corner: end-evening and the demo close.

Own module because ``_view.py`` is at the 250-line cap. Pure painting, like the
rest of the view: the press is handed in.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from leetcode_guard import _glyphs as g
from leetcode_guard._tooltip import add_tooltip

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
    add_tooltip(button, "end")
    button.place(relx=1.0, x=-10, y=10, anchor="ne")
    return button


def install_demo_close_button(
    parent: tk.Misc, config: LockConfig, on_close: Callable[[], None]
) -> tk.Button:
    """The escape that makes a demo safe to run.

    Installed on the **surface**, not on the root. With
    ``overrideredirect=True`` the root is a full-screen backdrop and gatelock's
    per-output Toplevels sit on top of it, so a button placed on the root is
    drawn behind them and is invisible and unclickable. Caught by screenshotting
    the demo rather than by any test -- which is exactly why the demo gets
    screenshotted.
    """
    button = tk.Button(
        parent,
        text=g.CLOSE,
        font=config.font("title"),
        width=2,
        fg=config.palette.on_fill,
        bg=config.palette.danger,
        command=on_close,
        relief="flat",
    )
    add_tooltip(button, "close")
    button.place(x=10, y=10)
    return button
