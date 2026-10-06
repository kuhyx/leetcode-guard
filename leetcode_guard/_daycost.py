"""What a day costs, and where a day begins.

Four decisions live here and each was easy to get subtly wrong.

**Local, not UTC.** ``date.weekday()`` on a UTC timestamp would start charging
the weekend price at 01:00 or 02:00 local time on Sunday morning, and stop
charging it at the same hour on Monday -- neither of which is a weekend as the
user experiences one. UTC is used for ``created_at`` and HLC ordering, and
nowhere else.

**Three tiers around one knob.** Since 2026-10-07 Tue/Wed/Thu cost the base
(2), Mon/Fri one more (3) and Sat/Sun twice it (4); see :func:`tiered`. The
base is the what-if knob, so ``--price`` still means "the Tue-Thu cost".
Credits stay fungible: one earned on Wednesday can be spent on Saturday, it
just goes half as far.

**Prices are dated, never re-written.** ``_debt`` prices every uncharged day
since the epoch through :func:`day_cost`, so a flat re-price would have minted
debt out of past days. Each era keeps its own prices; :data:`INTERIM_DATE` and
:data:`REPRICE_DATE` say where the second and the current one begin.

**The debt surcharge skips Tue-Thu.** Debt adds one credit to Mon/Fri/Sat/Sun
only (:func:`surcharge_applies`); a Tue-Thu day costs its plain price however
much is owed. Repayment is therefore earned on the dearer days alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
import functools
import logging
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable

_logger: Final = logging.getLogger(__name__)

_DAY_ABBREVIATIONS: Final = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
""":meth:`datetime.date.weekday` order: Monday is 0."""

_SURCHARGE_FREE_DAYS: Final = frozenset({1, 2, 3})
"""Tue, Wed, Thu: the days a debt never makes dearer."""


@dataclass(frozen=True)
class Pricing:
    """One era of day prices.

    Attributes:
        costs: What each weekday costs, Monday first
            (:meth:`datetime.date.weekday` order).
        penalty_cost: What a day costs once a missed wake-alarm ring has taken
            its Tue-Thu discount away: the price of a Friday in this era.
    """

    costs: tuple[int, int, int, int, int, int, int]
    penalty_cost: int

    def cost(self, day: date) -> int:
        """How many credits ``day`` consumes under this pricing."""
        return self.costs[day.weekday()]

    def penalised_cost(self, day: date) -> int:
        """``day``'s price with the Tue-Thu discount gone; never below its own."""
        return max(self.cost(day), self.penalty_cost)

    def describe(self) -> str:
        """``Tue/Wed/Thu cost 2, Mon/Fri cost 3, Sat/Sun cost 4``."""
        groups = []
        for cost in sorted(set(self.costs)):
            days = zip(_DAY_ABBREVIATIONS, self.costs, strict=True)
            names = "/".join(name for name, c in days if c == cost)
            groups.append(f"{names} cost {cost}")
        return ", ".join(groups)


def tiered(base_cost: int) -> Pricing:
    """The current price shape around ``base_cost`` (the Tue-Thu price)."""
    mid = base_cost + 1
    return Pricing(
        costs=(mid, base_cost, base_cost, base_cost, mid, 2 * base_cost, 2 * base_cost),
        penalty_cost=mid,
    )


ORIGINAL_PRICING: Final = Pricing(costs=(1, 1, 1, 1, 1, 2, 2), penalty_cost=2)
"""Weekdays 1, Saturday and Sunday 2 -- the prices from the gate's start."""

INTERIM_PRICING: Final = Pricing(costs=(2, 1, 1, 1, 2, 2, 2), penalty_cost=2)
"""Tue/Wed/Thu 1, Mon/Fri/Sat/Sun 2. Chosen 2026-09-21 knowing it lands the
837 free Easy problems on 2028-01-21, three weeks past the 31.12.2027 target;
replaced 2026-10-07 by :data:`CURRENT_PRICING`."""

INTERIM_DATE: Final = date(2026, 9, 21)
"""First day :data:`INTERIM_PRICING` applies."""

CURRENT_BASE: Final = 2
"""The Tue-Thu price now in force, and the what-if default."""

CURRENT_PRICING: Final = tiered(CURRENT_BASE)
"""Tue/Wed/Thu 2, Mon/Fri 3, Sat/Sun 4. Chosen 2026-10-06: the earlier
acceptance of a three-week miss was replaced by a deliberately steeper gate."""

REPRICE_DATE: Final = date(2026, 10, 7)
"""First day :data:`CURRENT_PRICING` applies. Earlier days keep their era's
prices, so the debt they are owed at does not change."""


def surcharge_applies(day: date) -> bool:
    """Whether outstanding debt adds a credit to ``day`` (not on Tue-Thu)."""
    return day.weekday() not in _SURCHARGE_FREE_DAYS


def local_now(*, now: datetime | None = None) -> datetime:
    """The current local wall-clock time, or an injected stand-in.

    Spelled ``datetime.now(tz=timezone.utc).astimezone()`` rather than the
    shorter ``datetime.now()`` because the latter returns a naive datetime,
    which the lint profile rejects and which silently compares wrong against
    anything timezone-aware.
    """
    return now if now is not None else datetime.now(tz=UTC).astimezone()


def local_today(*, now: datetime | None = None) -> date:
    """Today's local calendar date."""
    return local_now(now=now).date()


def pricing_for(day: date, *, current: Pricing = CURRENT_PRICING) -> Pricing:
    """The era ``day`` falls in; ``current`` stands in for the live prices."""
    if day >= REPRICE_DATE:
        return current
    return INTERIM_PRICING if day >= INTERIM_DATE else ORIGINAL_PRICING


def day_cost(day: date, *, current: Pricing = CURRENT_PRICING) -> int:
    """How many credits ``day`` consumes."""
    return pricing_for(day, current=current).cost(day)


def what_if(base_cost: int) -> Callable[[date], int]:
    """A :func:`day_cost` whose current era has another Tue-Thu price.

    Past days keep their real prices -- a what-if changes nothing that is owed.
    """
    return functools.partial(day_cost, current=tiered(base_cost))


def base_terms(day: date) -> tuple[int, int]:
    """``(per_base, flat)`` with ``tiered(p).cost(day) == per_base * p + flat``."""
    flat = tiered(0).cost(day)
    return tiered(1).cost(day) - flat, flat


def day_key(day: date) -> str:
    """The canonical ``YYYY-MM-DD`` string used in ledger entry ids."""
    return day.isoformat()


def parse_day(text: str) -> date | None:
    """Read a ``YYYY-MM-DD`` string back, or ``None`` if it is not one.

    Returning ``None`` rather than raising is deliberate: an unparsable date in
    the ledger must be reported and ignored, never allowed to abort the load.
    Aborting would mean the whole ledger is unreadable, which reads as a zero
    balance -- an accidental permanent lock.
    """
    try:
        return date.fromisoformat(text)
    except ValueError:
        _logger.warning("ignoring an unparsable day %r", text)
        return None


def weekday_name(day: date) -> str:
    """The day's English name, for the lock surface."""
    return day.strftime("%A")
