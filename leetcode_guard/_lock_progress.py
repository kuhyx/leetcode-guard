"""The lock's poll signs progress while the day is still short.

The one-minute harvester stands aside while a lock holds the instance lock, so
this is the only writer then. Split out of ``_lock_poll.py`` for the 250-line
cap. Never in the demo (its ledger is thrown away every run) and never when the
lock may not write; :func:`~leetcode_guard._gate_progress.apply_progress`
declines a paid or stood-down day and never raises.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._gate_progress import apply_progress

if TYPE_CHECKING:
    from leetcode_guard._gate import GateDecision
    from leetcode_guard._ledger_io import Ledger
    from leetcode_guard._lock_deps import GuardDeps


def record_progress(
    ledger: Ledger, decision: GateDecision, deps: GuardDeps, *, demo: bool
) -> None:
    """Sign "done of target" for ``decision`` when the lock may write."""
    if demo or not deps.write_ledger:
        return
    apply_progress(
        ledger,
        decision,
        deps.ledger_path,
        now=deps.moment(),
        key_file=deps.key_file,
    )
