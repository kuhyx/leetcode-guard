"""What the missed days are owed, and how much of it has been repaid.

A day the gate never charged -- because the PC was off, or because the lock
sat unsatisfied until it died -- used to cost nothing. From
:data:`DEBT_START_DATE` it is *owed* instead, at the price it would have cost,
and every gated day is one credit dearer until the debt is gone. That extra
credit is the repayment.

Debt is **derived, never stored**. The ledger is walked for charges, the
calendar for the days between the epoch and today, and the free-day pool for
the days that were legitimately off. There is no ``debt:`` entry to forge or
delete: deleting the ledger makes every day since the epoch uncharged, which
grows the debt rather than clearing it, and back-filling ``charge:<date>``
entries for missed days is off the table because that is the exact key
:func:`~leetcode_guard._gate.decide` unlocks on.

Repayment follows the *credit* rule from ``_balance`` (trusted entries only),
because it relieves the user the way a credit does. The full ``amount`` of an
untrusted charge still counts as spent -- discarding it would be a refund --
but its surcharge repays nothing, so inflating a forged charge only costs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Final

from leetcode_guard._balance import is_trusted
from leetcode_guard._constants import DEBT_START_DATE
from leetcode_guard._daycost import day_cost, day_key, parse_day, weekday_name
from leetcode_guard._ledger import CHARGE

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import date

    from leetcode_guard._ledger_io import Ledger

SURCHARGE: Final = 1
"""How many extra credits a day costs while debt is outstanding. One, by
decision, whatever the day's own price: a Tue-Thu day goes from 1 to 2 and a
doubled day from 2 to 3 until the account is back on track."""


@dataclass(frozen=True)
class Debt:
    """The position on missed days, all in credits.

    Attributes:
        owed: What every uncharged, non-free day since the epoch would have
            cost, summed.
        repaid: The surcharges already paid on trusted charges.
        missed_days: How many calendar days make up ``owed``.
    """

    owed: int
    repaid: int
    missed_days: int

    @property
    def outstanding(self) -> int:
        """What is still to be repaid.

        Never negative: overpaying (a charge surcharged before a free day
        cleared the debt) is not a credit.
        """
        return max(0, self.owed - self.repaid)

    @property
    def surcharge(self) -> int:
        """The extra cost today carries.

        :data:`SURCHARGE` while anything is outstanding, otherwise nothing.
        """
        return SURCHARGE if self.outstanding else 0


NO_DEBT: Final = Debt(owed=0, repaid=0, missed_days=0)
"""The position when the rule is not in force: the demo, and tests that are
not about debt."""


def compute_debt(
    ledger: Ledger,
    *,
    day: date,
    is_free: Callable[[date], bool],
    start: date | None = None,
) -> Debt:
    """Derive the debt as of ``day``.

    The window is ``[start, day)`` -- today is never owed while it is still
    today; it becomes debt tomorrow if it goes uncharged. Repayment is read
    from the same window, so moving the epoch forgives both sides at once:
    a surcharge paid before it neither counts nor is owed. The free-day
    lookup is only consulted for days that carry no charge, so its cost
    scales with the days actually missed, not with the calendar.

    Args:
        ledger: The loaded ledger, verification attached.
        day: Today's local date.
        is_free: Whether a given day was in the shared free-day pool.
        start: The epoch. Defaults to :data:`DEBT_START_DATE`; injectable so
            tests can place it inside the fixture week.

    Returns:
        The position. Nothing is written.
    """
    epoch = DEBT_START_DATE if start is None else start
    charged_days: set[str] = set()
    repaid = 0
    for entry in ledger.entries.values():
        if entry.kind != CHARGE:
            continue
        charged_days.add(entry.day)
        charged_on = parse_day(entry.day)
        if (
            charged_on is None
            or charged_on < epoch
            or not is_trusted(entry, integrity_ok=ledger.integrity_ok)
        ):
            continue
        repaid += max(0, entry.amount - day_cost(charged_on))

    owed = 0
    missed_days = 0
    cursor = epoch
    while cursor < day:
        if day_key(cursor) not in charged_days and not is_free(cursor):
            owed += day_cost(cursor)
            missed_days += 1
        cursor += timedelta(days=1)

    return Debt(owed=owed, repaid=repaid, missed_days=missed_days)


def cost_phrase(day: date, cost: int, debt: Debt) -> str:
    """``Tuesday costs 2 (1 +1 debt)``.

    The surcharge spelled out, because a quota that silently doubled reads as
    a bug.
    """
    if not debt.surcharge:
        return f"{weekday_name(day)} costs {cost}"
    return (
        f"{weekday_name(day)} costs {cost} "
        f"({cost - debt.surcharge} +{debt.surcharge} debt)"
    )


def debt_summary(debt: Debt) -> str:
    """``22 credits outstanding (18 missed days owed 22, 0 repaid)``.

    Prefix-free, for the column layouts that already say ``debt``.
    """
    plural = "" if debt.missed_days == 1 else "s"
    return (
        f"{debt.outstanding} credits outstanding ({debt.missed_days} missed "
        f"day{plural} owed {debt.owed}, {debt.repaid} repaid)"
    )


def debt_line(debt: Debt) -> str:
    """One sentence for the lock surface: what is owed and how it goes away."""
    if not debt.outstanding:
        return "No debt -- on track"
    return f"Debt: {debt_summary(debt)} -- +{debt.surcharge} per day until repaid"
