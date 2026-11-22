#!/usr/bin/env python3
"""Prove a lock button's tooltip stays visible while gatelock raises the surface.

**No unit test can answer this.** In the suite Tk is a MagicMock, so a tooltip
"shows" whether or not anything can see it. On a real lock gatelock's recovery
tick calls ``raise_all()`` -- ``lift()`` on every surface -- whenever the grab is
held. The first tooltip was its own Toplevel: it painted for half a second and
then sat buried under the surface for as long as the pointer rested on the
button (live demo, 2026-11-22). Only a real X server knows the stacking order.

So this builds a surface the way gatelock does (an ``overrideredirect``
Toplevel over the root), lifts it every tick, rests the real pointer on a
button with a tooltip, and asks X which window is on top where the tip is::

    xvfb-run -a -s "-screen 0 1600x1200x24" python3 -m scripts.verify_tooltip_stack
"""

from __future__ import annotations

import sys
import tkinter as tk
from typing import TYPE_CHECKING, Final

from leetcode_guard._tooltip import add_tooltip

if TYPE_CHECKING:
    from collections.abc import Iterator

RAISE_EVERY_MS: Final = 100
"""Faster than gatelock's recovery tick, so a buried tip cannot slip through."""

TIP_DELAY_MS: Final = 100
JUDGE_AFTER_MS: Final = 1500
"""Long enough for the tip to show and then survive a dozen raises."""

TIP_TEXT: Final = "probe"
SURFACE_GEOMETRY: Final = "600x300+0+0"
BUTTON_OFFSET_PX: Final = 10


def _descendants(widget: tk.Misc) -> Iterator[tk.Misc]:
    """Every widget under ``widget``, Toplevels included."""
    for child in widget.winfo_children():
        yield child
        yield from _descendants(child)


def _judge(root: tk.Tk) -> list[str]:
    """Return the failures: no tip mapped, or a tip some other window covers."""
    root.update()
    tips = [
        widget
        for widget in _descendants(root)
        if isinstance(widget, tk.Label)
        and widget.cget("text") == TIP_TEXT
        and widget.winfo_ismapped()
    ]
    if not tips:
        return ["no tooltip is mapped while the pointer rests on the button"]
    tip = tips[0]
    x = tip.winfo_rootx() + tip.winfo_width() // 2
    y = tip.winfo_rooty() + tip.winfo_height() // 2
    on_top = root.winfo_containing(x, y)
    if on_top is not tip:
        return [f"the tooltip is covered: X puts {on_top} on top at its centre"]
    return []


def main() -> int:
    """Hover a tooltip button on a constantly raised surface; judge the tip."""
    root = tk.Tk()
    root.geometry(SURFACE_GEOMETRY)
    surface = tk.Toplevel(root)
    surface.overrideredirect(boolean=True)
    surface.geometry(SURFACE_GEOMETRY)
    button = tk.Button(surface, text="X")
    button.place(x=BUTTON_OFFSET_PX, y=BUTTON_OFFSET_PX)
    add_tooltip(button, TIP_TEXT, delay_ms=TIP_DELAY_MS)

    def keep_raising() -> None:
        surface.lift()
        root.after(RAISE_EVERY_MS, keep_raising)

    failures: list[str] = []

    def finish() -> None:
        failures.extend(_judge(root))
        root.destroy()

    root.update()
    button.event_generate(
        "<Motion>",
        warp=True,
        x=button.winfo_width() // 2,
        y=button.winfo_height() // 2,
    )
    keep_raising()
    root.after(JUDGE_AFTER_MS, finish)
    root.mainloop()

    for failure in failures:
        print(f"  [FAIL] {failure}")
    if failures:
        return 1
    print("  [PASS] the tooltip stays on top of a surface raised every tick")
    return 0


if __name__ == "__main__":
    sys.exit(main())
