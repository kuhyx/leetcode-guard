"""What a day costs, and where a day begins.

Three decisions live here and each was easy to get subtly wrong.

**Local, not UTC.** ``date.weekday()`` on a UTC timestamp would start charging
the doubled price at 01:00 or 02:00 local time on Sunday morning, and stop
charging it at the same hour on Monday -- neither of which is a weekend as the
user experiences one. UTC is used for ``created_at`` and HLC ordering, and
nowhere else.

**Doubled days cost exactly twice the base.** Since 2026-09-21 Monday, Friday,
Saturday and Sunday are doubled (2) around a base of 1; before that only
Saturday and Sunday doubled. The factor is structural
(:attr:`Pricing.doubled_cost`), so the base is the one knob and "times two"
cannot drift back into "plus one". Credits stay fungible: one earned on
Wednesday can be spent on Saturday, it just goes half as far.

**Prices are dated, never re-written.** ``_debt`` prices every uncharged day
since the epoch through :func:`day_cost`, so a flat re-price would have minted
debt out of past Mondays and Fridays. Each era keeps its own prices and
:data:`REPRICE_DATE` says where the current one begins.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
import functools
import logging
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable

_logger: Final = logging.getLogger(__name__)

_DAY_ABBREVIATIONS: Final = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
""":meth:`datetime.date.weekday` order: Monday is 0."""


@dataclass(frozen=True)
class Pricing:
    """One era of day prices.

    Attributes:
        base_cost: What an ordinary day costs.
        doubled_days: :meth:`datetime.date.weekday` numbers that cost
            :attr:`doubled_cost` instead.
    """

    base_cost: int
    doubled_days: frozenset[int]

    @property
    def doubled_cost(self) -> int:
        """Twice the base, by rule -- never an independent number."""
        return 2 * self.base_cost

    def multiplier(self, day: date) -> int:
        """How many base units ``day`` costs: 2 on a doubled day, else 1."""
        return 2 if day.weekday() in self.doubled_days else 1

    def cost(self, day: date) -> int:
        """How many credits ``day`` consumes under this pricing."""
        return self.base_cost * self.multiplier(day)

    def with_base(self, base_cost: int) -> Pricing:
        """The same doubled days at another base -- the what-if knob."""
        return replace(self, base_cost=base_cost)

    def describe(self) -> str:
        """``Tue/Wed/Thu cost 2, Mon/Fri/Sat/Sun cost 4``."""
        single = "/".join(
            name
            for i, name in enumerate(_DAY_ABBREVIATIONS)
            if i not in self.doubled_days
        )
        doubled = "/".join(
            name for i, name in enumerate(_DAY_ABBREVIATIONS) if i in self.doubled_days
        )
        return f"{single} cost {self.base_cost}, {doubled} cost {self.doubled_cost}"


ORIGINAL_PRICING: Final = Pricing(base_cost=1, doubled_days=frozenset({5, 6}))
"""Weekdays 1, Saturday and Sunday 2 -- the prices from the gate's start."""

CURRENT_PRICING: Final = Pricing(base_cost=1, doubled_days=frozenset({0, 4, 5, 6}))
"""Tue/Wed/Thu 1, Mon/Fri/Sat/Sun 2. Chosen 2026-09-21 knowing it lands the
837 free Easy problems on 2028-01-21, three weeks past the 31.12.2027 target
-- a base of 2 would have landed in 2027-05 and then doubled every day for
seven months. The 33-problem gap is accepted, not overlooked."""

REPRICE_DATE: Final = date(2026, 9, 21)
"""First day :data:`CURRENT_PRICING` applies. Earlier days keep
:data:`ORIGINAL_PRICING`, so the debt they are owed at does not change."""


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
    return current if day >= REPRICE_DATE else ORIGINAL_PRICING


def day_cost(day: date, *, current: Pricing = CURRENT_PRICING) -> int:
    """How many credits ``day`` consumes."""
    return pricing_for(day, current=current).cost(day)


def what_if(base_cost: int) -> Callable[[date], int]:
    """A :func:`day_cost` whose current era has another base price.

    Past days keep their real prices -- a what-if changes nothing that is owed.
    """
    return functools.partial(day_cost, current=CURRENT_PRICING.with_base(base_cost))


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
