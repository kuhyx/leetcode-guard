# Copyright (c) 2026 Krzysztof Rudnicki
"""Tkinter tooltip helper (textgate: one word on hover).

Each interactive icon/button gets a one-word tooltip naming what it does.
"""

from __future__ import annotations

import tkinter as tk
from typing import Final

_TOPMOST_ON: Final = 1


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
        self._tip: tk.Toplevel | None = None
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
        x = self.widget.winfo_pointerx() + 10
        y = self.widget.winfo_pointery() + 10
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(boolean=True)
        tip.attributes("-topmost", _TOPMOST_ON)
        tip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tip,
            text=self.text,
            background="#1e1e1e",
            foreground="#d4d4d4",
            relief="solid",
            borderwidth=1,
            font=("TkDefaultFont", 9),
            padx=6,
            pady=2,
        )
        label.pack()
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
