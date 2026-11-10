"""Shapes drawn on a canvas instead of written as words or emoji.

The padlock replaces the old headline sentence ("Solve 2 LeetCode problems to
unlock"). It is *drawn*, not typed: the padlock character is a colour emoji
(U+1F512) and Tk 8.6 can crash on colour-emoji fonts. Two channels: the
shackle shape (closed vs lifted) and the colour (danger vs success).
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from gatelock import LockConfig

PADLOCK_PX: Final = 56

# Proportions of the icon box, so the shape scales with PADLOCK_PX.
_BODY_TOP = 0.54
_BODY_INSET = 0.14
_SHACKLE_INSET = 0.3
_SHACKLE_WIDTH = 0.1
_SHACKLE_TOP = 0.22
_LIFT = 0.14
"""How far an open shackle rises, as a share of the box; stays inside it."""


class Padlock:
    """A padlock icon that redraws itself closed (red) or open (green)."""

    def __init__(self, parent: tk.Misc, config: LockConfig) -> None:
        """Create the canvas; call :meth:`draw` to paint it."""
        self._config = config
        self.canvas = tk.Canvas(
            parent,
            width=PADLOCK_PX,
            height=PADLOCK_PX,
            bg=config.palette.bg,
            highlightthickness=0,
        )
        self.locked: bool | None = None
        """What is drawn now; ``None`` before the first paint."""

    def draw(self, *, locked: bool) -> None:
        """Paint the padlock; a no-op when it already shows ``locked``."""
        if self.locked is locked:
            return
        self.locked = locked
        palette = self._config.palette
        colour = palette.danger if locked else palette.success
        self.canvas.delete("all")
        self._body(colour)
        self._shackle(colour, locked=locked)
        self._keyhole(palette.bg)

    def _body(self, colour: str) -> None:
        size = PADLOCK_PX
        self.canvas.create_rectangle(
            size * _BODY_INSET,
            size * _BODY_TOP,
            size * (1 - _BODY_INSET),
            size - 2,
            fill=colour,
            outline=colour,
        )

    def _shackle(self, colour: str, *, locked: bool) -> None:
        """The arc and its legs.

        An open one is lifted and missing its left leg, which is what makes it
        read as open at a glance.
        """
        size = PADLOCK_PX
        left, right = size * _SHACKLE_INSET, size * (1 - _SHACKLE_INSET)
        top = size * _SHACKLE_TOP - (0 if locked else size * _LIFT)
        width = size * _SHACKLE_WIDTH
        self.canvas.create_arc(
            left,
            top,
            right,
            top + (right - left),
            start=0,
            extent=180,
            style="arc",
            outline=colour,
            width=width,
        )
        middle, body_top = top + (right - left) / 2, size * _BODY_TOP
        legs = (left, right) if locked else (right,)
        for x in legs:
            self.canvas.create_line(x, middle, x, body_top, fill=colour, width=width)

    def _keyhole(self, colour: str) -> None:
        size = PADLOCK_PX
        hole = size * 0.07
        centre_x, centre_y = size / 2, (size * _BODY_TOP + size) / 2
        self.canvas.create_oval(
            centre_x - hole,
            centre_y - hole,
            centre_x + hole,
            centre_y + hole,
            fill=colour,
            outline=colour,
        )
