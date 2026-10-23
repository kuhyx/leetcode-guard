"""The one-line status CLIs the tray icon uses.

``--state`` prints one word for the icon's colour, ``--summary`` one line for
its tooltip (and for the notification the tray shows when the status app's
launcher is missing). A bare call prints the summary.

These used to live in ``status_view.py`` beside a tkinter window; the window
is now the Flutter status app (``app/``), which reads the exported snapshot.
Nothing here writes anything: both lines are read from files on disk.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Final

from leetcode_guard._status_full import gather_full

if TYPE_CHECKING:
    from leetcode_guard._status_full import FullStatus

STATE_OK: Final = "ok"
STATE_WARN: Final = "warn"
STATE_LOCK: Final = "lock"


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
    costs = f"{gate.weekday} costs {gate.cost}"
    if gate.debt_outstanding:
        costs += f", debt {gate.debt_outstanding}"
    if gate.locked:
        plural = "" if gate.needed == 1 else "s"
        return f"LOCKED - solve {gate.needed} problem{plural} ({costs})"
    if gate.state == "not-started":
        return f"leetcode-guard: {gate.reason}"
    return f"Unlocked - {gate.available} credit(s) left ({costs})"


def main(argv: list[str] | None = None) -> int:
    """Entry point: ``--state`` prints the word, anything else the summary."""
    args = sys.argv[1:] if argv is None else argv
    full = gather_full()
    print(state_word(full) if "--state" in args else summary_line(full))
    return 0


if __name__ == "__main__":
    sys.exit(main())
