#!/usr/bin/env python3
"""Assert every lock screen fits a 1366x768 display.

The guard's surfaces ``place`` a centred frame, and a ``place``d frame takes
its *requested* size: when it is taller than the screen the parent shears
equal amounts off the top **and** the bottom, losing the headline and the
escape button together, with no scrollbar and nothing to say anything is
missing -- inside a lock that cannot be dismissed. So "it fits" is not a
preference here, it is the only thing keeping the screen readable.

Runs the real builders against a real (throwaway) X display, because widget
heights come from the font engine and nothing short of rendering can answer
this honestly:

    cd ~/leetcode-guard && python3 -m scripts.verify_screen_fits

Run as a *module*, not a path: ``-m`` puts the repo root on
``sys.path`` so ``leetcode_guard`` resolves from the checkout. Running it as a
path only works where the package happens to be pip-installed, which is
why it passed locally and died in CI.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

from gatelock import LockConfig, measure_fit, report_fit

from leetcode_guard._escape_flow import EscapeHatch, build_tracker
from leetcode_guard._view import build_guard_view
from leetcode_guard._viewmodel import ProblemLine, ViewModel

if TYPE_CHECKING:
    import tkinter as tk

    from gatelock import FitResult, ScrollableSurface

_logger = logging.getLogger(__name__)

INNER_ENV = "_SCREEN_FITS_CHECK_INNER"

# The panel this app has to fit: the machine it runs on.
WIDTH = 1366
HEIGHT = 768

# The worst realistic case: the maximum problems the lock offers at once, with
# long titles, plus every optional note line.
_MODEL = ViewModel(
    headline="Solve 1 LeetCode problem to unlock",
    balance_line="Credits 0  |  Monday costs 1  |  Debt 2",
    status_line="Watching for a solve... last checked 14:32",
    notes=(
        "Yesterday's solve landed after the daily cutoff and counted for today.",
        "The escape hatch becomes available again in 12 minutes.",
    ),
    problems=tuple(
        ProblemLine(
            label=f"{n}. Longest Substring Without Repeating Characters (Medium)",
            url=f"https://leetcode.com/problems/problem-{n}/",
        )
        for n in range(1, 6)
    ),
    unlocked=False,
    show_escape=True,
)


def reexec_under_xvfb() -> int:
    """Re-run this script on a throwaway X display, returning its exit code."""
    xvfb_run = shutil.which("xvfb-run")
    if xvfb_run is None:
        _logger.error(
            "xvfb-run not found. Install it with: sudo pacman -S --needed "
            "xorg-server-xvfb"
        )
        return 1
    env = dict(os.environ, **{INNER_ENV: "1"})
    return subprocess.run(
        [
            xvfb_run,
            "-a",
            # Bigger than the size under test, so the surface is sized by the
            # geometry the harness sets rather than clamped by the display.
            "-s",
            "-screen 0 1600x1200x24",
            sys.executable,
            "-m",
            "scripts.verify_screen_fits",
        ],
        check=False,
        cwd=Path(__file__).resolve().parent.parent,
        env=env,
    ).returncode


def _placed_child(parent: tk.Misc) -> tk.Misc:
    """Return the ``place``d descendant that carries the screen's height.

    ``place`` does not propagate a child's size to its parent, so measuring
    the parent would report an empty screen. Falls back to the parent itself
    when nothing is placed, which measures correctly for packed layouts.
    """
    for child in parent.winfo_children():
        if child.winfo_manager() == "place":
            return child
        found = _placed_child(child)
        if found is not child:
            return found
    return parent


def _build_lock(surface: ScrollableSurface) -> tk.Misc:
    """Paint the main lock screen and return the frame to measure."""
    build_guard_view(surface.content, LockConfig(), _MODEL, output_name="fit-check")
    return _placed_child(surface.content)


def _build_escape(surface: ScrollableSurface) -> tk.Misc:
    """Paint the escape-hatch form and return the frame to measure."""
    config = LockConfig()
    tracker = build_tracker(Path("/nonexistent/leetcode-guard-fit-check.json"))
    hatch = EscapeHatch(tracker, config, on_granted=lambda _reason: None)
    hatch.show(surface.content)
    return _placed_child(surface.content)


def measure_all() -> list[FitResult]:
    """Measure every lock screen at the supported size."""
    return [
        measure_fit("lock-surface", _build_lock, width=WIDTH, height=HEIGHT),
        measure_fit("escape-hatch", _build_escape, width=WIDTH, height=HEIGHT),
    ]


def main() -> int:
    """Measure every screen and fail if any of them overflows."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    if os.environ.get(INNER_ENV) != "1":
        return reexec_under_xvfb()

    _logger.info("Measuring every lock screen against a %dx%d panel:", WIDTH, HEIGHT)
    if report_fit(measure_all()):
        _logger.info("\nOK: every screen fits.")
        return 0
    _logger.error(
        "\nAt least one screen is taller than the display. A place-centred "
        "lock surface clips at BOTH edges when that happens, so the overflow "
        "is not merely hidden -- it is unrecoverable."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
