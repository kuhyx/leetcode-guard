"""What-if: a goal, a date, and the base price that connects them.

The question this answers is the one asked on 2026-09-20: "by how much do I
raise the Tue-Thu price to have solved N Easy problems by date T?" Three
inputs -- a base price, absolute per-difficulty targets, a date -- and both
readings of the answer: what the typed price forces by *T* and when it lands
the goal, and the smallest price that lands the goal on *T* itself.

Pure arithmetic on top of :func:`~leetcode_guard._projection.project`, using
the same pay-it-all reading of the debt so the numbers here agree with the
lines printed above them. A goal is *absolute* ("Easy reaches 837"), the way
the panel shows ``58 / 966``; what it still needs is the goal minus the solved
count, per difficulty, summed. One required credit is taken to be one new
problem, exactly as the projection assumes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
import math
from typing import TYPE_CHECKING

from leetcode_guard._daycost import CURRENT_PRICING, REPRICE_DATE, day_cost, what_if
from leetcode_guard._progress import DIFFICULTIES

if TYPE_CHECKING:
    from collections.abc import Callable

    from leetcode_guard._progress import Progress
    from leetcode_guard._projection import Projection

MIN_PRICE = 1
"""A base price below one is a free day by another name."""

LANDING_HORIZON_DAYS = 3650
"""How far past the last gated day the landing search looks before giving up.
Every gated day costs at least one credit, so a goal that has not landed
``needed`` gated days in only fails to if the calendar is nearly all free."""


@dataclass(frozen=True)
class Goal:
    """Absolute solved-count targets, per difficulty, for the ones that were set."""

    counts: dict[str, int]

    def needed(self, progress: Progress) -> int:
        """New solves the goal still requires, summed over difficulties."""
        return sum(
            max(0, count - progress.solved[name]) for name, count in self.counts.items()
        )

    def unreachable(self, progress: Progress) -> list[str]:
        """Difficulties whose target exceeds what exists on the site."""
        return [
            name
            for name in DIFFICULTIES
            if name in self.counts and self.counts[name] > progress.total[name]
        ]

    def beyond_easy(self) -> bool:
        """Whether a Medium or Hard target was set -- they wait on Easy."""
        return any(name in self.counts for name in DIFFICULTIES[1:])


@dataclass(frozen=True)
class Scenario:
    """The what-if, worked.

    Attributes:
        target: The date the what-if was worked for.
        base_cost: The price the user typed.
        needed: New solves the goal requires from where the counts stand.
        forced: What ``base_cost`` collects by the target (pay-it-all reading).
        lands_on: First day ``forced`` reaches ``needed`` at that price, which
            may be after the target; ``None`` when the horizon ran out.
        exact_price: The fractional base price that lands the goal on the
            target exactly; ``None`` when no priced day lies in range.
        minimal_price: The smallest whole price at or above ``exact_price``,
            never below :data:`MIN_PRICE`.
        minimal_lands_on: Where ``minimal_price`` lands the goal.
    """

    target: date
    base_cost: int
    needed: int
    forced: int
    lands_on: date | None
    exact_price: Fraction | None
    minimal_price: int | None
    minimal_lands_on: date | None

    @property
    def shortfall(self) -> int:
        """Solves the typed price leaves undone on the target date."""
        return max(0, self.needed - self.forced)


def landing_day(
    projection: Projection,
    needed: int,
    *,
    is_free: Callable[[date], bool],
    cost_of: Callable[[date], int],
) -> date | None:
    """The first day on which the demanded credits reach ``needed``.

    The same sum :func:`~leetcode_guard._projection.project` uses -- day
    prices plus the debt in full, less what is banked -- accumulated one day
    at a time from the projection's first day, past its target if need be.
    """
    collected = projection.debt - projection.available
    cursor = projection.first_day
    if collected >= needed:
        return cursor
    horizon = cursor + timedelta(days=needed + LANDING_HORIZON_DAYS)
    while cursor <= horizon:
        if not is_free(cursor):
            collected += cost_of(cursor)
            if collected >= needed:
                return cursor
        cursor += timedelta(days=1)
    return None


def exact_price(
    projection: Projection, needed: int, *, is_free: Callable[[date], bool]
) -> Fraction | None:
    """The base price at which the gated days up to the target sum to ``needed``.

    Days before :data:`REPRICE_DATE` keep their fixed price and are subtracted
    first; the rest count in base units (one or two per day). ``None`` when
    no day in range is priced in base units, so no price could land it.
    """
    fixed = units = 0
    cursor = projection.first_day
    while cursor <= projection.target:
        if not is_free(cursor):
            if cursor < REPRICE_DATE:
                fixed += day_cost(cursor)
            else:
                units += CURRENT_PRICING.multiplier(cursor)
        cursor += timedelta(days=1)
    if units == 0:
        return None
    remaining = needed - projection.debt + projection.available - fixed
    return Fraction(max(0, remaining), units)


def build_scenario(
    base_cost: int,
    goal: Goal,
    progress: Progress,
    projection: Projection,
    *,
    is_free: Callable[[date], bool],
) -> Scenario:
    """Work the what-if; ``projection`` is the one already computed at ``base_cost``."""
    needed = goal.needed(progress)
    exact = exact_price(projection, needed, is_free=is_free)
    minimal = None if exact is None else max(MIN_PRICE, math.ceil(exact))

    def lands(price: int) -> date | None:
        return landing_day(projection, needed, is_free=is_free, cost_of=what_if(price))

    return Scenario(
        target=projection.target,
        base_cost=base_cost,
        needed=needed,
        forced=projection.required,
        lands_on=lands(base_cost),
        exact_price=exact,
        minimal_price=minimal,
        minimal_lands_on=None if minimal is None else lands(minimal),
    )
