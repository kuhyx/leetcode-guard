"""Fan one logical widget out across every monitor.

The lock draws one surface per live output, but the *content* is one thing.
Building it per surface would mean running the paint code N times, and paint
code here is not a pure function -- it reads a decision and formats it.

So the flow body runs **once** and the widget factory fans out: each requested
widget is created N times behind a proxy that mirrors ``configure``, ``pack``
and ``destroy`` onto every copy. Trimmed from
``screen_locker/_surface_group.py``, which solved the same problem first.

Widgets are typed ``tk.Widget`` -- the real type, which genuinely carries
``configure``, ``pack``, ``pack_forget`` and ``destroy``. An earlier draft used
``Any`` to dodge a lint rule; that silenced the checker instead of telling it
the truth, and suppression comments are banned repo-wide for the same reason.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    import tkinter as tk


class WidgetGroup:
    """One logical widget, realised once per surface."""

    def __init__(self, widgets: list[tk.Widget]) -> None:
        self._widgets = widgets

    def __iter__(self) -> Iterator[tk.Widget]:
        return iter(self._widgets)

    def __len__(self) -> int:
        return len(self._widgets)

    @property
    def first(self) -> tk.Widget | None:
        """The primary surface's copy, if there is one.

        ``None`` is a legitimate answer: with zero live outputs the lock still
        holds the grab and simply shows nothing.
        """
        return self._widgets[0] if self._widgets else None

    def configure(self, **kwargs: object) -> None:
        """Apply the same configuration to every copy."""
        for widget in self._widgets:
            widget.configure(**kwargs)

    def pack(self, **kwargs: object) -> None:
        """Pack every copy."""
        for widget in self._widgets:
            widget.pack(**kwargs)

    def pack_forget(self) -> None:
        """Hide every copy."""
        for widget in self._widgets:
            widget.pack_forget()

    def destroy(self) -> None:
        """Destroy every copy and forget them."""
        for widget in self._widgets:
            widget.destroy()
        self._widgets = []


class FrameGroup:
    """The set of per-output containers currently on screen.

    Keyed by output name so a monitor unplugged mid-lock can be dropped without
    disturbing the others.
    """

    def __init__(self) -> None:
        self._frames: dict[str, tk.Misc] = {}

    def add(self, output_name: str, frame: tk.Misc) -> None:
        """Register one surface's container."""
        self._frames[output_name] = frame

    def discard(self, output_name: str) -> None:
        """Forget a surface that has gone away."""
        self._frames.pop(output_name, None)

    def clear(self) -> None:
        """Forget every surface."""
        self._frames.clear()

    def get(self, output_name: str) -> tk.Misc | None:
        """One surface's container, or ``None``."""
        return self._frames.get(output_name)

    @property
    def names(self) -> tuple[str, ...]:
        """Which outputs currently carry a surface."""
        return tuple(self._frames)

    def __len__(self) -> int:
        return len(self._frames)

    def __iter__(self) -> Iterator[tk.Misc]:
        return iter(self._frames.values())
