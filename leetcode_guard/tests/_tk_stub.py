"""The Tk stand-in every test runs against.

Split out of ``conftest.py`` for the 250-line cap. The autouse fixture that
installs this still lives in ``conftest.py``; what moved is the data it needs
-- which modules to patch, and the geometry numbers a mocked canvas has to
answer with.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    import pytest


_GATELOCK_TK_MODULES = (
    "gatelock.widgets",
    "gatelock._scrollable",
)
"""gatelock modules that build widgets on *this* app's behalf.

Deliberately separate from ``TK_MODULES``: that list is defined by
``grep -l '^import tkinter as tk' leetcode_guard/*.py`` and must keep matching
it exactly. These are gatelock's own modules, and the same reasoning applies
for the same reason ``_gatelock_fixtures`` already patches
``gatelock._surfaces.tk.Toplevel`` -- patching ``tk`` inside *this* package is
not enough once a shared library builds the buttons and the scroll viewport.
Without them, ``tk_mock.Button``/``tk_mock.Label`` never see the widgets the
status panel is made of.
"""

# Sizes for the mocked viewport. Content must be *shorter* than the canvas:
# ScrollableSurface.finalize() logs at warning when content overflows, and a
# warning on every render of a panel that legitimately scrolls would be noise
# that teaches the reader to ignore the one message that matters.
_FAKE_VIEWPORT_PX = 900
_FAKE_CONTENT_PX = 400
_FAKE_SCREEN_PX = 1080
_FAKE_SCROLLBAR_PX = 16


def fake_gatelock_widgets(monkeypatch: pytest.MonkeyPatch, fake: MagicMock) -> None:
    """Point gatelock's widget builders at ``fake`` and give them real numbers.

    ``ScrollableSurface`` does genuine geometry arithmetic (``min``/``max`` and
    comparisons over ``winfo_*``), which a bare ``MagicMock`` cannot satisfy --
    it raises ``TypeError: '<' not supported between instances of MagicMock``.
    So the widgets it builds answer their measurement calls with ints.
    """
    canvas = fake.Canvas.return_value
    canvas.winfo_height.return_value = _FAKE_VIEWPORT_PX
    canvas.winfo_width.return_value = _FAKE_VIEWPORT_PX
    canvas.winfo_screenwidth.return_value = _FAKE_SCREEN_PX
    canvas.winfo_screenheight.return_value = _FAKE_SCREEN_PX
    canvas.cget.return_value = 0
    canvas.bbox.return_value = (0, 0, _FAKE_VIEWPORT_PX, _FAKE_CONTENT_PX)
    frame = fake.Frame.return_value
    frame.winfo_reqheight.return_value = _FAKE_CONTENT_PX
    frame.winfo_reqwidth.return_value = _FAKE_VIEWPORT_PX
    frame.winfo_children.return_value = []
    fake.Scrollbar.return_value.winfo_reqwidth.return_value = _FAKE_SCROLLBAR_PX
    for name in _GATELOCK_TK_MODULES:
        module = importlib.import_module(name)
        monkeypatch.setattr(module, "tk", fake, raising=True)


TK_MODULES = (
    "leetcode_guard._view",
    "leetcode_guard._view_problems",
    "leetcode_guard._escape_form",
    "leetcode_guard._status_sections",
    "leetcode_guard._study",
    "leetcode_guard._study_resume",
    "leetcode_guard._study_steps",
    "leetcode_guard._study_strip",
    "leetcode_guard.status_view",
)
"""Every module that does ``import tkinter as tk``.

Any new one must be added here **in the same commit**. Miss one and the suite
does not fail -- it opens a real fullscreen window, or worse, hangs holding a
grab.

The list runs both ways: ``_lock`` was removed when its last widget call moved
to ``_view.install_demo_close_button``, because patching a ``tk`` attribute a
module no longer has raises at fixture time and fails every test in the suite.
Verify with ``grep -l '^import tkinter as tk' leetcode_guard/*.py`` after any
move.
"""
