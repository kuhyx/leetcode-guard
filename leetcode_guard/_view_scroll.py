"""A fixed-height, scrollable viewport for the suggestion list.

The surface still has the pixel budget ``PROBLEM_DISPLAY_LIMIT`` was sized for,
so the viewport is exactly as tall as that many rows and everything else is
reached by scrolling. Rows are created lazily, a batch at a time, as the user
nears the end: building all ~4000 would cost seconds and a lot of memory per
monitor, for rows almost nobody scrolls to.

Wheel events are bound on every widget inside the viewport, not just the
canvas: X delivers the wheel to the widget under the pointer, which is nearly
always a row label or an Open button. ``Button-4``/``Button-5`` are what X11
sends; ``MouseWheel`` is kept for completeness.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING, Final

from leetcode_guard._view_problems import ROW_BATCH, append_rows

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import LockConfig

    from leetcode_guard._view import GuardView

GROW_WHEN_PAST: Final = 0.8
"""Scroll fraction past which the next batch of rows is built."""

_WHEEL_UNITS: Final = 2


class ScrollArea:
    """Canvas + scrollbar + inner frame, sized to a number of rows."""

    def __init__(
        self,
        parent: tk.Misc,
        config: LockConfig,
        *,
        on_near_end: Callable[[], None],
    ) -> None:
        """Build the empty viewport; rows are packed into :attr:`inner`."""
        bg = config.palette.field_bg
        self.outer = tk.Frame(parent, bg=bg)
        self.canvas = tk.Canvas(self.outer, bg=bg, highlightthickness=0, bd=0)
        self.scrollbar = tk.Scrollbar(
            self.outer, orient="vertical", command=self._on_scrollbar
        )
        self.canvas.configure(yscrollcommand=self._on_view_moved)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner.bind("<Configure>", self._on_inner_resized)
        self.canvas.bind("<Configure>", self._on_canvas_resized)
        self._on_near_end = on_near_end
        self._grow_pending = False
        self.bind_wheel(self.canvas)
        self.bind_wheel(self.inner)

    def bind_wheel(self, widget: tk.Misc) -> None:
        """Make ``widget`` scroll the list when the wheel turns over it."""
        widget.bind("<Button-4>", lambda _e: self.scroll(-_WHEEL_UNITS))
        widget.bind("<Button-5>", lambda _e: self.scroll(_WHEEL_UNITS))
        widget.bind(
            "<MouseWheel>",
            lambda e: self.scroll(-_WHEEL_UNITS if e.delta > 0 else _WHEEL_UNITS),
        )

    def fit_rows(self, count: int, visible: int) -> None:
        """Size the viewport to ``visible`` of the ``count`` rows built.

        Measured, not computed from font metrics: a row's height is the taller
        of its label and its button plus padding, and only Tk knows that. Rows
        are uniform -- one unwrapped line and one button each -- so the share
        of the built height is the height of that many rows. Shows the
        scrollbar only when there is more than fits.
        """
        self.inner.update_idletasks()
        total = int(self.inner.winfo_reqheight())
        height = total if count <= visible else total * visible // count
        self.canvas.configure(height=max(height, 1))
        self._fit_width()
        if count > visible:
            self.scrollbar.pack(side="right", fill="y")
        else:
            self.scrollbar.pack_forget()

    def scroll(self, units: int) -> None:
        """Scroll by ``units`` (negative is up)."""
        self.canvas.yview_scroll(units, "units")

    def _on_scrollbar(self, *args: str) -> None:
        self.canvas.yview(*args)

    def _on_view_moved(self, first: str, last: str) -> None:
        self.scrollbar.set(first, last)
        if float(last) >= GROW_WHEN_PAST and not self._grow_pending:
            # Deferred: this runs inside Tk's own scroll bookkeeping, and
            # packing new rows from here would re-enter it.
            self._grow_pending = True
            self.canvas.after_idle(self._grow)

    def _grow(self) -> None:
        self._grow_pending = False
        self._on_near_end()

    def _on_inner_resized(self, _event: object) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._fit_width()

    def _fit_width(self) -> None:
        """Widen to the widest row built so far; never narrow.

        A canvas does not take its child's size the way a frame does -- left
        alone it sits at Tk's default width and clips each long title together
        with its Open button. Never narrowing keeps the panel from jumping
        sideways as rows are rebound or built.
        """
        wanted = self.inner.winfo_reqwidth()
        if wanted > int(self.canvas.cget("width")):
            self.canvas.configure(width=wanted)

    def _on_canvas_resized(self, event: tk.Event[tk.Canvas]) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)


def grow_rows(view: GuardView, config: LockConfig) -> int:
    """Build the next batch of rows from the lines last painted.

    Returns:
        How many rows were added. Zero when the list is already fully built,
        or when it is showing the no-problems stand-in.
    """
    have = len(view.problem_labels)
    extra = view.lines[have : have + ROW_BATCH]
    if not extra or not view.lines or view.scroll is None:
        return 0
    labels, buttons = append_rows(
        view.scroll.inner, config, extra, view.on_open, bind=view.scroll.bind_wheel
    )
    view.problem_labels.extend(labels)
    view.open_buttons.extend(buttons)
    if view.on_reveal is not None:
        view.on_reveal(len(view.problem_labels))
    return len(labels)
