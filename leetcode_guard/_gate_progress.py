"""Progress toward today's price: one pure function, one writer, the strip.

"Done N of target M" for a day the gate still holds. ``earned_time`` cannot
know this guard's price (the day's cost, the debt surcharge, the workday
penalty, Easy 1 / Medium 2 / Hard 4), so the guard signs the fact and the
shutdown bonus is paid in proportion to it.

:func:`progress_counts` is the only place the two numbers are computed. The
writer (:func:`apply_progress`) and the study strip's dots both call it, so the
screen and the signed row cannot disagree.

**Inert by construction.** The row is kind ``progress``; ``compute_balance``,
``compute_debt`` and ``check_clock`` read credits and charges only, so a row
(honest, forged or edited) moves no decision, charge, credit, debt or lock.
Nothing here is read back by the guard. Writing is best effort and runs after
the credit or charge it describes is already saved: a failure costs the row,
is logged at warning, and never reaches the caller.
"""

from __future__ import annotations

from collections import defaultdict
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard._balance import counts_toward_balance, credit_value
from leetcode_guard._daycost import day_key
from leetcode_guard._difficulty import load_weights
from leetcode_guard._gate_state import GateState
from leetcode_guard._ledger import CREDIT
from leetcode_guard._ledger_entries import progress_entry
from leetcode_guard._ledger_io import append, save_ledger

if TYPE_CHECKING:
    from datetime import date, datetime
    from pathlib import Path

    from leetcode_guard._difficulty import WeightTable
    from leetcode_guard._gate import GateDecision
    from leetcode_guard._ledger_io import Ledger

_logger: Final = logging.getLogger(__name__)


def earned_today(ledger: Ledger, *, day: date, weights: WeightTable | None) -> int:
    """Counted credits whose row is dated ``day``, in the balance's unit.

    By the row's ``day``, not its id: a finish credit (``theory-done:...``) has
    no day in its id and is still one of today's. Trusted rows only, by the
    balance's own rule, so a forged or foreign credit is never earned.
    """
    today = day_key(day)
    tally: defaultdict[str, int] = defaultdict(int)  # difficulty mix: unused
    return sum(
        credit_value(entry, weights, tally)
        for entry in ledger.entries.values()
        if entry.kind == CREDIT
        and entry.day == today
        and counts_toward_balance(entry, integrity_ok=ledger.integrity_ok)
    )


def progress_counts(
    ledger: Ledger, decision: GateDecision, *, weights: WeightTable | None
) -> tuple[int, int]:
    """(done, target) for ``decision.day``.

    ``done`` is the most of what was earned today, what the gate counts as
    available (credits banked earlier are work done ahead) and zero, so a
    negative carried balance never shrinks today's own earnings. ``target`` is
    ``done`` plus what the gate still says is missing. Display and writer both
    call this; it reads nothing but its arguments.
    """
    earned = earned_today(ledger, day=decision.day, weights=weights)
    done = max(earned, decision.balance.available, 0)
    return done, done + decision.needed


def apply_progress(
    ledger: Ledger,
    decision: GateDecision,
    path: Path,
    *,
    now: datetime,
    key_file: Path | None = None,
) -> bool:
    """Sign "done of target" for a day the gate still holds; never raises.

    Writes only for a gated, uncharged day that is still short
    (:attr:`GateState.LOCKED_INSUFFICIENT`) with at least one credit done. An
    untrusted clock is not that state, so a rolled-back date signs nothing.
    A row with the same id is not written again, and an unsigned one (key
    unreadable) is not written at all: it is worthless to ``earned_time`` and,
    the ledger being append-only, its id would block the signed row for good.

    Returns:
        Whether a row was written. ``False`` for every decline and failure; a
        failure is logged at warning or above.
    """
    try:
        if decision.state is not GateState.LOCKED_INSUFFICIENT:
            return False
        return _write(ledger, decision, path, now=now, key_file=key_file)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _logger.warning(
            "progress row not written: %s", type(exc).__name__, exc_info=True
        )
        return False


def _write(
    ledger: Ledger,
    decision: GateDecision,
    path: Path,
    *,
    now: datetime,
    key_file: Path | None,
) -> bool:
    """The body of :func:`apply_progress`, free to raise."""
    weights = load_weights(key_file=key_file)
    done, target = progress_counts(ledger, decision, weights=weights)
    if done < 1 or ledger.has(f"progress:{day_key(decision.day)}:{done}:{target}"):
        return False
    row = progress_entry(
        for_day=decision.day, done=done, target=target, now=now, key_file=key_file
    )
    if row.signature is None:
        _logger.warning("progress row not signed (HMAC key unreadable): skipped")
        return False
    append(ledger, [row])
    return save_ledger(path, ledger)
