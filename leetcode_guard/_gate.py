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
from leetcode_guard._daycost import day_cost, day_key, pricing_for
from leetcode_guard._debt import NO_DEBT, Debt, cost_phrase
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

    UNLOCKED_FREE_DAY = "free-day"
    """Today is in the shared free-day pool. No lock, and no charge either --
    a day off is not paid for out of the credit balance."""

    UNLOCKED_SICK_DAY = "sick-day"
    """Today is in the shared *sick*-day pool (not the free-day pool): no lock,
    no charge, nothing added to the debt."""


@dataclass(frozen=True)
class GateDecision:
    """The verdict, with everything needed to explain or apply it."""

    state: GateState
    day: date
    cost: int
    """What today costs in full: the day's price plus the debt surcharge."""

    balance: Balance
    debt: Debt
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


def _standing_down(
    day: date, *, free_day: bool, sick_day: bool
) -> tuple[GateState, str] | None:
    """Why the gate does nothing today, when it does nothing.

    Free and sick are separate pools and stay separate verdicts.
    """
    if free_day:
        return GateState.UNLOCKED_FREE_DAY, "today is a free day"
    if sick_day:
        return GateState.UNLOCKED_SICK_DAY, "today is a sick day"
    if day < GATE_START_DATE:
        return (
            GateState.UNLOCKED_NOT_STARTED,
            f"the gate does not start until {GATE_START_DATE}",
        )
    return None


def decide(
    ledger: Ledger,
    *,
    day: date,
    now: datetime,
    key_file: Path | None = None,
    free_day: bool = False,
    debt: Debt = NO_DEBT,
    workday_penalty: bool = False,
    sick_day: bool = False,
) -> GateDecision:
    """Work out whether today is settled, settleable, or locked.

    Order matters. The clock check comes first because it invalidates the
    "already charged" shortcut that would otherwise fire beneath it -- and
    the free-day check sits *after* it deliberately: if the system date has
    moved backwards, the date a free day is claimed for is exactly as
    untrustworthy as everything else, so a tampered clock still locks.

    Args:
        ledger: The loaded ledger.
        day: Today's local date.
        now: Current time, for stamping a new charge.
        key_file: HMAC key override, for tests.
        free_day: Whether ``day`` is in the shared free-day pool. Passed in
            rather than looked up, so this function stays pure: ledger in,
            verdict out, no clock and no filesystem.
        debt: The missed-day position, computed by the caller for the same
            reason. While anything is outstanding today costs one credit more,
            and that credit is the repayment.
        workday_penalty: Whether a missed wake-alarm ring on a prior
            Tue/Wed/Thu cost ``day`` its own Tue/Wed/Thu discount. Losing the
            discount, not an added surcharge -- a day already priced at the
            penalty rate (Fri, from a Thursday miss) is unaffected. Ignored on
            a sick day.
        sick_day: Whether ``day`` is sick and does not keep ``leetcode``
            (``_sick.leetcode_stands_down``). Checked after the clock, like
            ``free_day``. A charge on the day repays as on any other day.

    Returns:
        The decision. Nothing is written.
    """
    balance = compute_balance(ledger)
    pricing = pricing_for(day)
    penalised = workday_penalty and not sick_day
    base_cost = pricing.penalised_cost(day) if penalised else day_cost(day)
    surcharge = debt.surcharge_on(day)
    cost = base_cost + surcharge
    costs = cost_phrase(day, cost, debt)

    def stand_down(state: GateState, reason: str) -> GateDecision:
        return GateDecision(
            state=state,
            day=day,
            cost=cost,
            balance=balance,
            debt=debt,
            needed=0,
            charge=None,
            reason=reason,
        )

    verdict = check_clock(ledger, day=day)
    if not verdict.trusted:
        return GateDecision(
            state=GateState.LOCKED_CLOCK_UNTRUSTED,
            day=day,
            cost=cost,
            balance=balance,
            debt=debt,
            needed=cost,
            charge=None,
            reason=verdict.reason,
        )
    if standing := _standing_down(day, free_day=free_day, sick_day=sick_day):
        return stand_down(*standing)
    if ledger.has(f"charge:{day_key(day)}"):
        return stand_down(GateState.UNLOCKED_ALREADY_CHARGED, _ALREADY)

    if balance.available >= cost:
        return GateDecision(
            state=GateState.UNLOCKED_CHARGED_NOW,
            day=day,
            cost=cost,
            balance=balance,
            debt=debt,
            needed=0,
            charge=charge_entry(day, now=now, key_file=key_file, surcharge=surcharge),
            reason=f"{balance.available} credits available, {costs}",
        )

    return GateDecision(
        state=GateState.LOCKED_INSUFFICIENT,
        day=day,
        cost=cost,
        balance=balance,
        debt=debt,
        needed=cost - balance.available,
        charge=None,
        reason=f"{balance.available} credits available but {costs}",
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
    the overdraft carries -- an escaped day is forgiven, not free. No surcharge:
    a forgiven day repays nothing, so the missed-day debt stands as it was.

    Returns:
        Whether the ledger was written.
    """
    entry = charge_entry(day, now=now, source=source, key_file=key_file)
    if ledger.has(entry.entry_id):
        return False
    append(ledger, [entry])
    return save_ledger(path, ledger)
