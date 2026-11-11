"""Gate-decision and view-model shortcuts shared by the day-kind test modules.

Free, sick and focus days all reach the gate through a ``DayContext`` on a
fixed ``NOW``; these builders keep that call in one place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._gate import decide, settle_day
from leetcode_guard._ledger import SOURCE_ESCAPE
from leetcode_guard._ledger_entries import charge_entry
from leetcode_guard._viewmodel import build_viewmodel
from leetcode_guard._viewmodel_source import ViewSource
from leetcode_guard.tests._ledger_fixtures import MONDAY, NOW
from leetcode_guard.tests.test_viewmodel import (
    CHECKED_AT,
    OK_PROBE,
    SIGNED_OUT,
    pool_of,
)

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

    from leetcode_guard._gate import DayContext, GateDecision
    from leetcode_guard._ledger_io import Ledger
    from leetcode_guard._viewmodel import ViewModel


def decide_with(
    ledger: Ledger, key_file: Path, context: DayContext, *, day: date = MONDAY
) -> GateDecision:
    """Decide *day* at ``NOW`` under *context*.

    Args:
        ledger: The ledger to decide over.
        key_file: The HMAC key to verify it with.
        context: What kind of day it is (free, sick, focus, penalised).
        day: The day being decided.

    Returns:
        The gate's decision.
    """
    return decide(ledger, day=day, now=NOW, key_file=key_file, context=context)


def view_of(decision: GateDecision) -> ViewModel:
    """The lock's view model for *decision* with an empty pool and no sign-in.

    Args:
        decision: The gate decision to render.

    Returns:
        The view model.
    """
    return build_viewmodel(
        decision,
        ViewSource(pool_of(), SIGNED_OUT, limit=10),
        OK_PROBE,
        checked_at=CHECKED_AT,
    )


def settle_escape(ledger: Ledger, path: Path, key_file: Path) -> bool:
    """Settle Monday with the charge a granted escape writes.

    Args:
        ledger: The ledger to settle in place.
        path: Where the ledger is saved.
        key_file: The HMAC key to sign the charge with.

    Returns:
        What ``settle_day`` returns: whether a new charge was saved.
    """
    return settle_day(
        ledger,
        charge_entry(MONDAY, now=NOW, source=SOURCE_ESCAPE, key_file=key_file),
        path,
    )
