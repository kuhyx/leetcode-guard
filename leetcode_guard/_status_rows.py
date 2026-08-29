"""The two row primitives every status section draws with.

Split out of ``_status_sections.py`` for the 250-line cap. Both section files
draw the same two shapes -- a heading and a wrapped body line -- and the wrap
width is shared state set once per render, so it lives with them rather than
being passed through every call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gatelock import DEFAULT_WRAP, RowStyle, heading, row

if TYPE_CHECKING:
    import tkinter as tk

    from gatelock import LockConfig, TypeRole


__all__ = ["DEFAULT_WRAP", "section_heading", "section_row", "set_wrap"]

_wrap_state = {"width": DEFAULT_WRAP}


def set_wrap(wrap: int) -> None:
    """Fix the wrap width for the sections about to be drawn.

    Clamped: a window narrower than 320px wraps every line to a column of
    single words, which is worse than overflowing.
    """
    _wrap_state["width"] = max(320, wrap)


def section_heading(parent: tk.Misc, config: LockConfig, text: str) -> None:
    """A section title, from gatelock's shared widget set."""
    heading(parent, config, text)


def section_row(
    parent: tk.Misc,
    config: LockConfig,
    text: str,
    *,
    color: str | None = None,
    role: TypeRole = "label",
) -> None:
    """One line of body text, wrapped to the current window width."""
    row(
        parent,
        config,
        text,
        RowStyle(color=color, role=role, wrap=_wrap_state["width"]),
    )
