"""kuhy's shared credit logo in the corner of each lock surface.

kuhy, 2026-11-21: his logo goes in every program, lockers included. The widget
is ``kuhy_credit.tk`` from kuhyx/utils, never a copy. A click on the logo opens
a small "Created by kuhy" panel; a click on the panel opens the site in a
browser tab, which stays behind the fullscreen lock until the lock closes, so
the credit opens no way past the gate.

On its own module, not inside ``_view.py``: ``KuhyCredit`` subclasses a real
``tk.Canvas`` and cannot be built over the mocked Tk the suite runs on, so the
test fixtures swap this module's ``KuhyCredit`` for a mock.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kuhy_credit.tk import KuhyCredit

if TYPE_CHECKING:
    import tkinter as tk

    from gatelock import LockConfig


def place_credit(parent: tk.Misc, config: LockConfig) -> KuhyCredit:
    """Put the dark credit logo in ``parent``'s bottom-right corner.

    Placed, not packed, so it overlays the corner without shifting the
    centred lock content.
    """
    pad = config.space("xl")
    credit = KuhyCredit(parent, theme="dark", size=config.type_px("display"))
    credit.place(relx=1, rely=1, x=-pad, y=-pad, anchor="se")
    return credit
