"""The study strip's dot counts. Display only.

The strip draws one filled dot per credit done and one hollow dot per credit
still owed. Both come from the same pure function the signed progress row is
written from (:func:`leetcode_guard._gate_progress.progress_counts`): filled is
``done`` (earned today, or banked earlier when that is more), hollow is
``target - done``. The screen and the row cannot disagree.

Derived at read time from the ledger the lock already holds and by the
balance's own rule, so a forged or foreign row never fills a dot. Nothing is
stored. **Nothing that decides, charges or credits may import this**: the strip
would turn from a picture of the day into an input to it. The pure function
lives decider-side for that reason, and ``test_display_only_imports.py`` bans
this module from every decider, transitively.

"Cannot read" is ``None`` (the strip draws no filled dot), never ``0``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard._difficulty import load_weights
from leetcode_guard._gate_progress import progress_counts

if TYPE_CHECKING:
    from pathlib import Path

    from leetcode_guard._gate import GateDecision
    from leetcode_guard._ledger_io import Ledger

_logger: Final = logging.getLogger(__name__)


def strip_counts(
    ledger: Ledger, decision: GateDecision, *, key_file: Path | None
) -> tuple[int, int | None]:
    """(hollow, filled) for the strip; filled is ``None`` when it cannot read.

    Hollow is at least 1 (a lock with nothing owed shows no dots at all, and
    the strip is only up while something is). Never raises (``Exception``
    only): a bug here costs the filled dots, never the strip, and so never the
    lock.
    """
    try:
        done, target = progress_counts(
            ledger, decision, weights=load_weights(key_file=key_file)
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _logger.warning("progress count failed: %s", type(exc).__name__, exc_info=True)
        return max(1, decision.needed), None
    return max(1, target - done), done
