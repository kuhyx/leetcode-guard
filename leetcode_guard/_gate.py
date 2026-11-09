"""The gate decision: lock, or don't.

:func:`decide` is pure -- ledger in, verdict out, nothing written and no clock
read. Writing is :func:`apply_decision`'s job. Keeping them apart is what makes
the whole day-cost algorithm testable as a table rather than through a
filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from leetcode_guard._balance import Balance, compute_balance
from leetcode_guard._clock_guard import check_clock
from leetcode_guard._constants import GATE_START_DATE
from leetcode_guard._daycost import day_cost, day_key, pricing_for
from leetcode_guard._debt import NO_DEBT, Debt, cost_phrase
from leetcode_guard._gate_state import GateState
from leetcode_guard._ledger_entries import charge_entry
from leetcode_guard._ledger_io import Ledger, append, save_ledger

if TYPE_CHECKING:
    from datetime import date, datetime
    from pathlib import Path

    from leetcode_guard._difficulty import WeightTable
    from leetcode_guard._ledger import LedgerEntry


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


@dataclass(frozen=True)
class DayContext:
    """What :func:`decide` is told about today, rather than looking it up.

    Passed in so ``decide`` stays pure -- ledger in, verdict out, no clock and
    no filesystem; :func:`~leetcode_guard._gate_today.decide_today` does the
    lookups. The defaults are an ordinary day with nothing owed.
    """

    free_day: bool = False
    """Whether the day is in the shared free-day pool. Checked after the clock:
    a tampered clock still locks."""

    debt: Debt = NO_DEBT
    """The missed-day position. While anything is outstanding today costs one
    credit more, and that credit is the repayment."""

    workday_penalty: bool = False
    """Whether a missed wake-alarm ring on a prior Tue/Wed/Thu cost the day its
    own Tue/Wed/Thu discount. Losing the discount, not an added surcharge -- a
    day already priced at the penalty rate (Fri, from a Thursday miss) is
    unaffected. Ignored on a sick day (one that keeps leetcode still pays it)
    and on a focus day."""

    sick_day: bool = False
    """Whether the day is sick and does not keep ``leetcode``
    (``_sick.leetcode_stands_down``). A charge on it repays as on any other."""

    focus_day: str | None = None
    """The active focus project's name when it stands the gate down (and no
    real sick day does); the verdict is ``focus-day`` and the day costs 0."""

    weights: WeightTable | None = None
    """Difficulty rows pricing each credit (Easy 1, Medium 2, Hard 4); ``None``
    prices every credit flat at 1."""


ORDINARY_DAY: Final = DayContext()


def _standing_down(day: date, context: DayContext) -> tuple[GateState, str] | None:
    """Why the gate does nothing today, when it does nothing.

    Free and sick are separate pools and stay separate verdicts.
    """
    if context.free_day:
        return GateState.UNLOCKED_FREE_DAY, "today is a free day"
    if context.focus_day is not None:
        return GateState.UNLOCKED_FOCUS_DAY, f"focus day: {context.focus_day}"
    if context.sick_day:
        return GateState.UNLOCKED_SICK_DAY, "today is a sick day"
    if day < GATE_START_DATE:
        return (
            GateState.UNLOCKED_NOT_STARTED,
            f"the gate does not start until {GATE_START_DATE}",
        )
    return None


def _price(day: date, context: DayContext) -> tuple[int, int]:
    """Today's full cost and the debt surcharge folded into it."""
    penalised = (
        context.workday_penalty and not context.sick_day and context.focus_day is None
    )
    base_cost = pricing_for(day).penalised_cost(day) if penalised else day_cost(day)
    surcharge = context.debt.surcharge_on(day)
    if context.focus_day is not None:
        return 0, surcharge
    return base_cost + surcharge, surcharge


def decide(
    ledger: Ledger,
    *,
    day: date,
    now: datetime,
    key_file: Path | None = None,
    context: DayContext = ORDINARY_DAY,
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
        context: The free/sick/focus flags, debt, workday penalty and credit
            weights for ``day`` (see :class:`DayContext`).

    Returns:
        The decision. Nothing is written.
    """
    balance = compute_balance(ledger, context.weights)
    cost, surcharge = _price(day, context)

    def verdict(
        state: GateState,
        reason: str,
        *,
        needed: int = 0,
        charge: LedgerEntry | None = None,
    ) -> GateDecision:
        return GateDecision(
            state=state,
            day=day,
            cost=cost,
            balance=balance,
            debt=context.debt,
            needed=needed,
            charge=charge,
            reason=reason,
        )

    clock = check_clock(ledger, day=day)
    if not clock.trusted:
        return verdict(GateState.LOCKED_CLOCK_UNTRUSTED, clock.reason, needed=cost)
    if standing := _standing_down(day, context):
        return verdict(*standing)
    if ledger.has(f"charge:{day_key(day)}"):
        return verdict(GateState.UNLOCKED_ALREADY_CHARGED, _ALREADY)

    costs = cost_phrase(day, cost, context.debt)
    if balance.available >= cost:
        return verdict(
            GateState.UNLOCKED_CHARGED_NOW,
            f"{balance.available} credits available, {costs}",
            charge=charge_entry(day, now=now, key_file=key_file, surcharge=surcharge),
        )
    return verdict(
        GateState.LOCKED_INSUFFICIENT,
        f"{balance.available} credits available but {costs}",
        needed=cost - balance.available,
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


def settle_day(ledger: Ledger, entry: LedgerEntry, path: Path) -> bool:
    """Mark a day as settled without spending credits.

    Used by the escape hatch and by the classified-outage path, with ``entry``
    the day's :func:`charge_entry` stamped with that ``source``. The charge is
    still recorded at full cost, so :attr:`Balance.available` goes negative and
    the overdraft carries -- an escaped day is forgiven, not free. No surcharge:
    a forgiven day repays nothing, so the missed-day debt stands as it was.

    Returns:
        Whether the ledger was written.
    """
    if ledger.has(entry.entry_id):
        return False
    append(ledger, [entry])
    return save_ledger(path, ledger)
