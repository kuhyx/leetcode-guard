"""The gate decision: lock, or don't.

:func:`decide` is pure -- ledger in, verdict out, nothing written and no clock
read. Writing is :func:`apply_decision`'s job. Keeping them apart is what makes
the whole day-cost algorithm testable as a table rather than through a
filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass
import enum
from typing import TYPE_CHECKING, Final

from leetcode_guard._balance import Balance, compute_balance
from leetcode_guard._clock_guard import check_clock
from leetcode_guard._constants import GATE_START_DATE
from leetcode_guard._daycost import day_cost, day_key, weekday_name
from leetcode_guard._ledger_entries import charge_entry
from leetcode_guard._ledger_io import Ledger, append, save_ledger

if TYPE_CHECKING:
    from datetime import date, datetime
    from pathlib import Path

    from leetcode_guard._ledger import LedgerEntry


class GateState(enum.Enum):
    """Why the gate reached its verdict."""

    UNLOCKED_NOT_STARTED = "not-started"
    """Today is before :data:`GATE_START_DATE`. The gate is installed but not
    yet in force."""

    UNLOCKED_ALREADY_CHARGED = "already-charged"
    """Today was settled by an earlier run. Re-running is a no-op, which is
    what makes the afternoon retry safe."""

    UNLOCKED_CHARGED_NOW = "charged"
    """Enough credit was available; this run spent it."""

    LOCKED_INSUFFICIENT = "locked"
    """Not enough credit. Solve something."""

    LOCKED_CLOCK_UNTRUSTED = "locked-clock"
    """The system date moved backwards past a settled day."""


@dataclass(frozen=True)
class GateDecision:
    """The verdict, with everything needed to explain or apply it."""

    state: GateState
    day: date
    cost: int
    balance: Balance
    needed: int
    """How many more credits today requires. Zero when unlocked."""

    charge: LedgerEntry | None
    """The entry to persist, iff the state is
    :attr:`GateState.UNLOCKED_CHARGED_NOW`."""

    reason: str

    @property
    def locked(self) -> bool:
        """Whether the PC should be locked."""
        return self.state in {
            GateState.LOCKED_INSUFFICIENT,
            GateState.LOCKED_CLOCK_UNTRUSTED,
        }


_ALREADY: Final = "today is already paid for"


def decide(
    ledger: Ledger,
    *,
    day: date,
    now: datetime,
    key_file: Path | None = None,
) -> GateDecision:
    """Work out whether today is settled, settleable, or locked.

    Order matters. The clock check comes first because it invalidates the
    "already charged" shortcut that would otherwise fire beneath it.

    Args:
        ledger: The loaded ledger.
        day: Today's local date.
        now: Current time, for stamping a new charge.
        key_file: HMAC key override, for tests.

    Returns:
        The decision. Nothing is written.
    """
    balance = compute_balance(ledger)
    cost = day_cost(day)

    verdict = check_clock(ledger, day=day)
    if not verdict.trusted:
        return GateDecision(
            state=GateState.LOCKED_CLOCK_UNTRUSTED,
            day=day,
            cost=cost,
            balance=balance,
            needed=cost,
            charge=None,
            reason=verdict.reason,
        )

    if day < GATE_START_DATE:
        return GateDecision(
            state=GateState.UNLOCKED_NOT_STARTED,
            day=day,
            cost=cost,
            balance=balance,
            needed=0,
            charge=None,
            reason=f"the gate does not start until {GATE_START_DATE}",
        )

    if ledger.has(f"charge:{day_key(day)}"):
        return GateDecision(
            state=GateState.UNLOCKED_ALREADY_CHARGED,
            day=day,
            cost=cost,
            balance=balance,
            needed=0,
            charge=None,
            reason=_ALREADY,
        )

    if balance.available >= cost:
        return GateDecision(
            state=GateState.UNLOCKED_CHARGED_NOW,
            day=day,
            cost=cost,
            balance=balance,
            needed=0,
            charge=charge_entry(day, now=now, key_file=key_file),
            reason=(
                f"{balance.available} credits available, "
                f"{weekday_name(day)} costs {cost}"
            ),
        )

    return GateDecision(
        state=GateState.LOCKED_INSUFFICIENT,
        day=day,
        cost=cost,
        balance=balance,
        needed=cost - balance.available,
        charge=None,
        reason=(
            f"{balance.available} credits available but {weekday_name(day)} "
            f"costs {cost}"
        ),
    )


def apply_decision(ledger: Ledger, decision: GateDecision, path: Path) -> bool:
    """Persist a decision's charge, if it has one.

    Returns:
        Whether anything was written. ``False`` for decisions that carry no
        charge -- not a failure, just nothing to do.
    """
    if decision.charge is None:
        return False
    append(ledger, [decision.charge])
    return save_ledger(path, ledger)


def settle_day(
    ledger: Ledger,
    *,
    day: date,
    now: datetime,
    source: str,
    path: Path,
    key_file: Path | None = None,
) -> bool:
    """Mark a day as settled without spending credits.

    Used by the escape hatch and by the classified-outage path. The charge is
    still recorded at full cost, so :attr:`Balance.available` goes negative and
    the debt carries -- an escaped day is forgiven, not free.

    Returns:
        Whether the ledger was written.
    """
    entry = charge_entry(day, now=now, source=source, key_file=key_file)
    if ledger.has(entry.entry_id):
        return False
    append(ledger, [entry])
    return save_ledger(path, ledger)
