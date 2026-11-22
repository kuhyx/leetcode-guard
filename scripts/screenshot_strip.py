#!/usr/bin/env python3
r"""Photograph the study strip alone, at a chosen earned + owed count.

``screenshot_lock.sh`` and ``screenshot_states.py`` cannot show it: the strip
only exists after Open stands the lock down and spawns a browser. So this puts
``build_strip`` on a real Tk root, on a throwaway X server, with the counts you
give it, and saves the crop. Tk is a MagicMock in the suite, so a dot grid that
clips or overlaps is invisible there; only a picture shows it::

    env -u DISPLAY xvfb-run -a -s "-screen 0 1600x1200x24" \\
        python3 -m scripts.screenshot_strip EARNED OWED OUT.png [--verifying]

Refuses the live display. Prints the window's size and the dot geometry.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from typing import Final

from gatelock import LockConfig, OutputRect

from leetcode_guard._strip_dots import layout
from leetcode_guard._study_strip import build_strip
from leetcode_guard._study_strip_text import StripText

SCREEN: Final = OutputRect(0, 0, 1600, 1200)
SETTLE_MS: Final = 700
CROP: Final = "400x420+1200+0"
"""The strip's corner of the screen (top-right), with room for a tall grid."""


def main(argv: list[str]) -> int:
    """Render, capture, quit."""
    display = os.environ.get("DISPLAY", "")
    if not display or display.startswith(":0"):
        sys.stderr.write("refusing to open a window on the live display\n")
        return 2
    earned, owed, out = int(argv[1]), int(argv[2]), argv[3]
    text = StripText(needed=owed, earned=earned, verifying="--verifying" in argv)
    root = tk.Tk()
    root.geometry("1600x1200+0+0")
    root.configure(bg="#8a8f98")  # a backdrop the strip must stand out from
    strip = build_strip(root, LockConfig(), text, rect=SCREEN, on_back=root.quit)

    def capture() -> None:
        strip.window.lift()  # no window manager here: stack it by hand
        root.update()
        subprocess.run(
            ["import", "-window", "root", "-crop", CROP, "+repage", out],
            check=True,
        )
        root.quit()

    root.update_idletasks()
    root.update()
    strip.window.update_idletasks()
    grid = layout(text.filled, text.hollow, width=strip.window.winfo_reqwidth())
    sys.stdout.write(
        f"window {strip.window.winfo_width()}x{strip.window.winfo_height()} "
        f"dots {len(grid.dots)} diameter {grid.diameter}px gap {grid.gap}px\n"
    )
    root.after(SETTLE_MS, capture)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
