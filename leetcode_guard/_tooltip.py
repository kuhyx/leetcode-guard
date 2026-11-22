# Copyright (c) 2026 Krzysztof Rudnicki
"""Tkinter tooltip helper (textgate: one word on hover).

Each icon-only button gets a one-word tooltip naming what it does.

The tip is a Label ``place()``d inside the button's own toplevel (the lock
surface), never a Toplevel of its own. gatelock's recovery tick lifts every
surface while the grab is held, so a separate tip window painted for half a
second and then stayed buried under the surface (live demo, 2026-11-22).
Inside the surface it rises with it. ``scripts/verify_tooltip_stack.py``
checks this on a real X server; the mocked suite cannot see stacking.
"""

from __future__ import annotations

import tkinter as tk
from typing import Final

_POINTER_GAP_PX: Final = 10


class Tooltip:
    """A hover tooltip for a widget."""

    def __init__(
        self,
        widget: tk.Misc,
        text: str,
        *,
        delay_ms: int = 500,
    ) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._job: str | None = None
        self._tip: tk.Label | None = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._hide)
        widget.bind("<ButtonPress>", self._hide)

    def _schedule(self, _event: tk.Event[tk.Misc]) -> None:
        if self._job is not None:
            return
        self._job = self.widget.after(self.delay_ms, self._show)

    def _show(self) -> None:
        self._job = None
        if self._tip is not None:
            return
        top = self.widget.winfo_toplevel()
        tip = tk.Label(
            top,
            text=self.text,
            background="#1e1e1e",
            foreground="#d4d4d4",
            relief="solid",
            borderwidth=1,
            font=("TkDefaultFont", 9),
            padx=6,
            pady=2,
        )
        # Below-right of the pointer, pulled back inside the surface's edges.
        x = self.widget.winfo_pointerx() - top.winfo_rootx() + _POINTER_GAP_PX
        y = self.widget.winfo_pointery() - top.winfo_rooty() + _POINTER_GAP_PX
        x = max(0, min(x, top.winfo_width() - tip.winfo_reqwidth()))
        y = max(0, min(y, top.winfo_height() - tip.winfo_reqheight()))
        tip.place(x=x, y=y)
        tip.lift()
        self._tip = tip

    def _hide(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        if self._job is not None:
            self.widget.after_cancel(self._job)
            self._job = None
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


def add_tooltip(widget: tk.Misc, text: str, *, delay_ms: int = 500) -> Tooltip:
    """Attach a one-word tooltip to ``widget``."""
    return Tooltip(widget, text, delay_ms=delay_ms)
