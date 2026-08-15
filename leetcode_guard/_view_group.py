"""Track the per-output containers the lock currently has on screen.

This file once also held a ``WidgetGroup`` -- a fan-one-widget-out-across-
every-monitor proxy, itself trimmed from ``screen_locker/_surface_group.py``,
which solved the same problem first. Four repos ended up with a copy, so it
moved to ``gatelock.WidgetGroup``; this one had no production call site at all
and was deleted rather than re-pointed. Reach for the shared class if the lock
ever needs to drive one logical widget across surfaces again.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    import tkinter as tk


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
