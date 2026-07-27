"""What a day costs, and where a day begins.

Two decisions live here and both were easy to get subtly wrong.

**Local, not UTC.** ``date.weekday()`` on a UTC timestamp would start charging
the weekend double at 01:00 or 02:00 local time on Sunday morning, and stop
charging it at the same hour on Monday -- neither of which is a weekend as the
user experiences one. UTC is used for ``created_at`` and HLC ordering, and
nowhere else.

**Weekend costs two, weekdays cost one.** Credits stay fungible: one earned on
Wednesday can be spent on Saturday, it just goes half as far.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import logging
from typing import Final

_logger: Final = logging.getLogger(__name__)

WEEKDAY_COST: Final = 1
WEEKEND_COST: Final = 2

WEEKEND_DAYS: Final = frozenset({5, 6})
""":meth:`datetime.date.weekday` numbering: Monday is 0, so Saturday is 5."""


def local_now(*, now: datetime | None = None) -> datetime:
    """The current local wall-clock time, or an injected stand-in.

    Spelled ``datetime.now(tz=timezone.utc).astimezone()`` rather than the
    shorter ``datetime.now()`` because the latter returns a naive datetime,
    which the lint profile rejects and which silently compares wrong against
    anything timezone-aware.
    """
    return now if now is not None else datetime.now(tz=timezone.utc).astimezone()


def local_today(*, now: datetime | None = None) -> date:
    """Today's local calendar date."""
    return local_now(now=now).date()


def day_cost(day: date) -> int:
    """How many credits ``day`` consumes."""
    return WEEKEND_COST if day.weekday() in WEEKEND_DAYS else WEEKDAY_COST


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
