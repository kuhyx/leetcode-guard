"""The study strip's dot grid: filled for credits earned, hollow for credits owed.

Geometry only, and a painter that draws it on a canvas it is handed (no Tk
import, so no ``TK_MODULES`` entry). Dots are big (the old row was a 16 px
glyph) and spaced (the gap is half a dot, at least :data:`MIN_GAP_PX`). The
grid wraps onto further rows, and when the rows would pass :data:`BUDGET_PX` the
dots shrink one pixel at a time down to :data:`MIN_PX`. Past that the grid
simply grows taller, and the strip with it (the window takes its height from its
contents): a dot is never clipped and never dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from leetcode_guard import _glyphs as g

if TYPE_CHECKING:
    import tkinter as tk

MAX_PX: Final = 26
MIN_PX: Final = 8
MIN_GAP_PX: Final = 4
MARGIN_PX: Final = 12
"""Free space left of the first and right of the last dot of a full row."""
PAD_PX: Final = 2
"""Above and below the grid, so a stroke is not cut at the canvas edge."""
BUDGET_PX: Final = 100
"""Height the dot rows may take before the dots start to shrink."""
CHECK_PX: Final = 28
"""Height of the canvas while it shows the solved check instead of dots."""
STROKE_PX: Final = 2


@dataclass(frozen=True)
class Dot:
    """One dot's top-left corner on the canvas."""

    x: int
    y: int
    filled: bool


@dataclass(frozen=True)
class DotGrid:
    """Every dot, how big they are and how tall the canvas must be."""

    diameter: int
    gap: int
    dots: tuple[Dot, ...]
    height: int


def _gap(diameter: int) -> int:
    return max(MIN_GAP_PX, diameter // 2)


def _per_row(diameter: int, width: int) -> int:
    gap = _gap(diameter)
    return max(1, (width - 2 * MARGIN_PX + gap) // (diameter + gap))


def _rows_height(total: int, diameter: int, width: int) -> int:
    rows = -(-total // _per_row(diameter, width))
    return rows * (diameter + _gap(diameter)) - _gap(diameter)


def layout(filled: int, hollow: int, *, width: int) -> DotGrid:
    """Place ``filled`` filled dots, then ``hollow`` hollow ones, in ``width`` px."""
    total = filled + hollow
    if total <= 0:
        return DotGrid(diameter=0, gap=0, dots=(), height=0)
    diameter = next(
        (
            size
            for size in range(MAX_PX, MIN_PX, -1)
            if _rows_height(total, size, width) <= BUDGET_PX
        ),
        MIN_PX,
    )
    gap = _gap(diameter)
    columns = _per_row(diameter, width)
    # A full row is centred; a short last row starts at the same left edge.
    left = (width - (min(columns, total) * (diameter + gap) - gap)) // 2
    dots = tuple(
        Dot(
            x=left + (index % columns) * (diameter + gap),
            y=PAD_PX + (index // columns) * (diameter + gap),
            filled=index < filled,
        )
        for index in range(total)
    )
    return DotGrid(
        diameter=diameter,
        gap=gap,
        dots=dots,
        height=_rows_height(total, diameter, width) + 2 * PAD_PX,
    )


@dataclass
class DotPainter:
    """Draws a :class:`DotGrid` on a canvas, only when a count has moved."""

    canvas: tk.Canvas
    width: int
    filled_colour: str
    hollow_colour: str
    check_font: tuple[str, int]
    painted: tuple[int, int] | None = None

    def paint(self, filled: int, hollow: int) -> None:
        """Redraw for these counts; both zero draws the solved check."""
        if self.painted == (filled, hollow):
            return
        self.painted = (filled, hollow)
        grid = layout(filled, hollow, width=self.width)
        self.canvas.delete("all")
        self.canvas.configure(height=grid.height or CHECK_PX)
        if not grid.dots:
            self.canvas.create_text(
                self.width // 2,
                CHECK_PX // 2,
                text=g.SOLVED,
                fill=self.hollow_colour,
                font=self.check_font,
            )
        for dot in grid.dots:
            self.canvas.create_oval(
                dot.x,
                dot.y,
                dot.x + grid.diameter,
                dot.y + grid.diameter,
                fill=self.filled_colour if dot.filled else "",
                outline=self.filled_colour if dot.filled else self.hollow_colour,
                width=STROKE_PX,
            )
