"""Read-only status window, plus the one-line CLIs the tray icon uses.

Mirrors screen-locker's workout-status window: same shape, same colours, same
``--summary`` / ``--state`` flags so the same kind of tray icon can drive it.

**Nothing here writes and nothing here fetches.** Opening or refreshing reads
files already on disk. That matters because this window is the thing you reach
for when the gate has done something surprising -- it must be safe to open at
any moment, including while the lock itself is up.

Closing is deliberately over-provided: a Close button, the Escape key, the
window manager's own close box, and clicking the tray icon again. A status
panel you cannot dismiss is a worse version of the problem this whole repo is
about.
"""

from __future__ import annotations

import sys
import tkinter as tk
from typing import TYPE_CHECKING, Final

from gatelock import LockConfig

from leetcode_guard._status_full import gather_full
from leetcode_guard._status_sections import DEFAULT_WRAP, render_sections

if TYPE_CHECKING:
    from collections.abc import Callable

    from leetcode_guard._status_full import FullStatus

_COLORS: Final = LockConfig()
"""Its defaults *are* the unified design system -- no overrides."""

_TITLE: Final = "LeetCode Status"
_MIN_WIDTH: Final = 560
_MIN_HEIGHT: Final = 400
_DEFAULT_GEOMETRY: Final = "980x900"
_WRAP_MARGIN: Final = 110
"""Padding plus the scrollbar, subtracted from the window width to get the
text wrap width."""

STATE_OK: Final = "ok"
STATE_WARN: Final = "warn"
STATE_LOCK: Final = "lock"


class StatusWindow:
    """The whole window. Rebuilt wholesale on every refresh."""

    def __init__(
        self,
        root: tk.Misc,
        snapshot: FullStatus,
        *,
        on_refresh: Callable[[], None],
        on_close: Callable[[], None],
    ) -> None:
        """Build the scrollable container and render ``snapshot`` immediately."""
        self.root = root
        self.on_refresh = on_refresh
        self.on_close = on_close
        self._canvas, self.container = _scrollable(root)
        self.render(snapshot)

    def render(self, snapshot: FullStatus) -> None:
        """Redraw everything from ``snapshot``."""
        for child in list(self.container.winfo_children()):
            child.destroy()

        heading = tk.Label(
            self.container,
            text=_TITLE,
            font=(_COLORS.font_family, 26, "bold"),
            fg=_COLORS.fg,
            bg=_COLORS.bg,
        )
        heading.pack(pady=(14, 10))

        render_sections(self.container, _COLORS, snapshot, wrap=self._wrap_width())
        self._buttons()
        self._canvas.update_idletasks()
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _wrap_width(self) -> int:
        """How wide text may run, from the window's real width.

        ``winfo_width`` reports 1 before the window is mapped, so the default
        geometry stands in for the first render and every later refresh picks
        up whatever the user resized to.
        """
        width = self.root.winfo_width()
        if width <= 1:
            return DEFAULT_WRAP
        return width - _WRAP_MARGIN

    def _buttons(self) -> None:
        """Refresh and Close, in that order."""
        row = tk.Frame(self.container, bg=_COLORS.bg)
        row.pack(pady=16)
        _button(row, "Refresh", _COLORS.field_bg, self.on_refresh).pack(
            side="left", padx=8
        )
        # Close is the accent action here, unlike in the lock: this window's
        # whole promise is that it goes away when you want it to.
        _button(row, "Close  (Esc)", _COLORS.accent, self.on_close).pack(
            side="left", padx=8
        )


def _button(
    parent: tk.Misc, text: str, background: str, command: Callable[[], None]
) -> tk.Button:
    """A button whose foreground is picked from its fill, never hardcoded."""
    # on_fill (dark ink) on accent/danger; near-white only on the dark greys.
    foreground = _COLORS.on_fill if background == _COLORS.accent else _COLORS.fg
    return tk.Button(
        parent,
        text=text,
        command=command,
        font=(_COLORS.font_family, 13),
        fg=foreground,
        bg=background,
        relief="flat",
        padx=14,
        pady=6,
    )


def _scrollable(root: tk.Misc) -> tuple[tk.Canvas, tk.Frame]:
    """A vertically scrollable frame.

    The panel shows everything the project knows, which is more than fits on a
    laptop screen -- without this the buttons fall off the bottom and the
    window becomes the un-closable thing it is meant not to be.
    """
    canvas = tk.Canvas(root, bg=_COLORS.bg, highlightthickness=0)
    scrollbar = tk.Scrollbar(root, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas, bg=_COLORS.bg)

    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _fit(event: tk.Event) -> None:
        canvas.itemconfigure(window_id, width=event.width)

    canvas.bind("<Configure>", _fit)
    inner.bind(
        "<Configure>",
        lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
    )
    canvas.bind_all("<Button-4>", lambda _e: canvas.yview_scroll(-2, "units"))
    canvas.bind_all("<Button-5>", lambda _e: canvas.yview_scroll(2, "units"))
    return canvas, inner


def state_word(full: FullStatus) -> str:
    """One word for the tray icon's colour.

    ``lock`` -- the gate would lock right now.
    ``warn`` -- unlocked, but nothing banked beyond today.
    ``ok``   -- unlocked with credit to spare.
    """
    if full.gate.locked:
        return STATE_LOCK
    if full.gate.available <= 0:
        return STATE_WARN
    return STATE_OK


def summary_line(full: FullStatus) -> str:
    """One line for the tray tooltip."""
    gate = full.gate
    if gate.locked:
        plural = "" if gate.needed == 1 else "s"
        return (
            f"LOCKED - solve {gate.needed} problem{plural} "
            f"({gate.weekday} costs {gate.cost})"
        )
    if gate.state == "not-started":
        return f"leetcode-guard: {gate.reason}"
    return (
        f"Unlocked - {gate.available} credit(s) left ({gate.weekday} costs {gate.cost})"
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point: ``--summary``/``--state`` print a line; else open the window."""
    args = sys.argv[1:] if argv is None else argv
    if "--summary" in args:
        print(summary_line(gather_full()))
        return 0
    if "--state" in args:
        print(state_word(gather_full()))
        return 0

    root = tk.Tk()
    root.title(_TITLE)
    root.configure(bg=_COLORS.bg)
    root.minsize(_MIN_WIDTH, _MIN_HEIGHT)
    root.geometry(_DEFAULT_GEOMETRY)

    def close() -> None:
        root.destroy()

    def refresh() -> None:
        window.render(gather_full())

    window = StatusWindow(root, gather_full(), on_refresh=refresh, on_close=close)
    # Three independent ways out, plus the tray toggle. See the module
    # docstring: a status panel you cannot dismiss is its own bug.
    root.protocol("WM_DELETE_WINDOW", close)
    root.bind("<Escape>", lambda _event: close())
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
