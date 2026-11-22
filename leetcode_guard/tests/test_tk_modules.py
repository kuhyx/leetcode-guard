# Copyright (c) 2026 Krzysztof Rudnicki
"""``TK_MODULES`` must name exactly the modules that import tkinter.

A module missing from the list is not patched, so the suite opens a real
window (or hangs on a grab) instead of failing; a stale entry fails every test
at fixture time. The grep in ``_tk_stub``'s docstring is now a test.
"""

from __future__ import annotations

from pathlib import Path

from leetcode_guard.tests._tk_stub import TK_MODULES

_PACKAGE = Path(__file__).resolve().parent.parent


def test_tk_modules_match_the_modules_that_import_tkinter() -> None:
    """Every ``import tkinter as tk`` module is listed, and nothing else."""
    importers = {
        f"leetcode_guard.{path.stem}"
        for path in _PACKAGE.glob("*.py")
        if any(
            line == "import tkinter as tk"
            for line in path.read_text(encoding="utf-8").splitlines()
        )
    }
    assert importers == set(TK_MODULES)
