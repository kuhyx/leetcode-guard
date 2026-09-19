"""How many problems you will have solved by a date, if you keep the gate fed.

Pure arithmetic over the pricing rules in ``_daycost`` and the debt position
in ``_debt``; nothing here reads a file or the network.

The question is "what does the lock demand between now and *T*, if I do every
day and also clear the debt". So the sum runs over every gated day up to and
including *T*, at each day's **base** price, plus the outstanding debt **in
full**, minus whatever is already banked. The daily surcharge is deliberately
not added on top: it *is* the debt being repaid, one credit per gated day, and
adding both would count the debt twice.

That "in full" is a choice the user made: the mechanism only ever collects one
credit of debt per gated day, so on a near date it would demand less than this
figure and leave the rest owed. Both numbers are reported -- the pay-it-all
target and what the rules will actually have collected by then -- so the
printed breakdown reproduces by hand.

Future solves are assumed to fill Easy first, then Medium, then Hard, because
that is the order the suggestion list serves them in. One required credit is
taken to be one *new* problem: the harvest mints a credit per accepted
submission id, so re-solving an old problem earns a credit without moving the
profile count -- the projection cannot see that and does not try to.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard._daycost import day_cost
from leetcode_guard._progress import DIFFICULTIES

if TYPE_CHECKING:
    from collections.abc import Callable

    from leetcode_guard._progress import Progress

_logger: Final = logging.getLogger(__name__)

_DOTTED_PARTS: Final = 3


def parse_target(text: str) -> date | None:
    """Read ``dd.mm.yyyy`` (as typed into the window) or ISO, else ``None``."""
    cleaned = text.strip()
    parts = cleaned.split(".")
    if len(parts) == _DOTTED_PARTS and all(part.isdigit() for part in parts):
        cleaned = f"{parts[2]}-{int(parts[1]):02d}-{int(parts[0]):02d}"
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        # Typed by a person, so the surface says "not a date"; logged too, for
        # the CLI form where the message and the log are one stream anyway.
        _logger.warning("ignoring an unparsable target date %r", text)
        return None


def default_target(today: date) -> date:
    """The last day of the current year -- the entry's starting value."""
    return date(today.year, 12, 31)


def format_target(day: date) -> str:
    """Render a date the way the entry expects it back."""
    return day.strftime("%d.%m.%Y")


@dataclass(frozen=True)
class Projection:
    """Everything the projection printed, with its working shown.

    Attributes:
        target: The date asked about.
        first_day: The first day the sum counts (tomorrow when today is
            already settled).
        gated_days: Days in ``first_day..target`` that are not free days.
        free_days: Days in that range the shared pool marks free.
        base_cost: Sum of each gated day's base price.
        debt: Outstanding debt, counted in full.
        available: Credits already banked, which the sum is reduced by.
        required: New solves needed under the pay-it-all reading.
        rules_demand: What the mechanism will actually have collected by
            ``target`` -- debt repays at most one credit per gated day.
        debt_left_by_rules: Debt still owed on ``target`` under the rules.
        projected: Solved count per difficulty after ``required`` new solves,
            Easy first; ``None`` when the current counts are unknown.
    """

    target: date
    first_day: date
    gated_days: int
    free_days: int
    base_cost: int
    debt: int
    available: int
    required: int
    rules_demand: int
    debt_left_by_rules: int
    projected: dict[str, int] | None


def _fill_easy_first(progress: Progress, new_solves: int) -> dict[str, int]:
    """Spread ``new_solves`` over the difficulties in serving order."""
    projected = dict(progress.solved)
    left = new_solves
    for name in DIFFICULTIES:
        take = min(left, progress.remaining(name))
        projected[name] += take
        left -= take
    return projected


@dataclass(frozen=True)
class Position:
    """The ledger facts the projection starts from, lifted off the snapshot."""

    today: date
    charged_today: bool
    available: int
    debt_outstanding: int


def project(
    target: date,
    position: Position,
    *,
    is_free: Callable[[date], bool],
    progress: Progress | None,
) -> Projection:
    """Compute the position on ``target``. See the module docstring."""
    today, debt_outstanding = position.today, position.debt_outstanding
    available = position.available
    first_day = today + timedelta(days=1) if position.charged_today else today
    gated = free = base_cost = 0
    cursor = first_day
    while cursor <= target:
        if is_free(cursor):
            free += 1
        else:
            gated += 1
            base_cost += day_cost(cursor)
        cursor += timedelta(days=1)
    required = max(0, base_cost + debt_outstanding - available)
    repaid_by_rules = min(debt_outstanding, gated)
    rules_demand = max(0, base_cost + repaid_by_rules - available)
    return Projection(
        target=target,
        first_day=first_day,
        gated_days=gated,
        free_days=free,
        base_cost=base_cost,
        debt=debt_outstanding,
        available=available,
        required=required,
        rules_demand=rules_demand,
        debt_left_by_rules=debt_outstanding - repaid_by_rules,
        projected=None if progress is None else _fill_easy_first(progress, required),
    )


def percent(solved: int, total: int) -> float:
    """``solved`` as a percentage of ``total``; 0 when there is no total."""
    return 0.0 if total <= 0 else 100.0 * solved / total
