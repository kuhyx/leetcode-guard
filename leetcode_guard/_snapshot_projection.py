"""Precompute the projection for every date the app's date control offers.

TODO-status-app.md decision 5: the pricing, free-day, sick-day and debt rules
stay in Python, so the app never projects -- it picks one of these keys. Each
key is :func:`~leetcode_guard._projection.project` at the live Tue-Thu price,
exactly what the tkinter window's "Project" button computes with its defaults
(``test_snapshot.py`` holds the two against each other).

The predicates are memoised per build: 99 targets walk ~37k days between
them, and each ``freedays``/``sickdays`` lookup reads its pool afresh.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
import functools
from typing import TYPE_CHECKING, Any, Final

import freedays

from leetcode_guard._daycost import CURRENT_BASE, what_if
from leetcode_guard._projection import project
from leetcode_guard._status_projection import position_of

if TYPE_CHECKING:
    from leetcode_guard._progress import Progress
    from leetcode_guard._projection import Projection
    from leetcode_guard._status import StatusSnapshot

DAILY_TARGETS: Final = 90
"""Today and the 89 days after it."""

MONTH_END_TARGETS: Final = 12
"""The last day of this month and of the 11 after it."""

_MONTHS: Final = 12


def _month_end(year: int, month: int) -> date:
    """The last day of ``month`` (1-based; may run past 12)."""
    year, index = year + (month - 1) // _MONTHS, (month - 1) % _MONTHS
    first_of_next = date(year + (index + 1) // _MONTHS, (index + 1) % _MONTHS + 1, 1)
    return first_of_next - timedelta(days=1)


def projection_targets(today: date) -> list[date]:
    """Every date with a precomputed projection, ascending, no repeats."""
    daily = {today + timedelta(days=offset) for offset in range(DAILY_TARGETS)}
    ends = {
        _month_end(today.year, today.month + offset)
        for offset in range(MONTH_END_TARGETS)
    }
    return sorted(daily | ends)


def projection_dict(projection: Projection) -> dict[str, Any]:
    """One projection as plain JSON data; ``projected`` stays ``None`` if unknown."""
    return {
        "target": projection.target.isoformat(),
        "first_day": projection.first_day.isoformat(),
        "gated_days": projection.gated_days,
        "free_days": projection.free_days,
        "sick_days": projection.sick_days,
        "base_cost": projection.base_cost,
        "debt": projection.debt,
        "available": projection.available,
        "required": projection.required,
        "rules_demand": projection.rules_demand,
        "debt_left_by_rules": projection.debt_left_by_rules,
        "projected": None
        if projection.projected is None
        else dict(projection.projected),
    }


def build_projections(
    snapshot: StatusSnapshot, progress: Progress | None
) -> dict[str, dict[str, Any]]:
    """Every target's projection, keyed by its ISO date."""
    base = position_of(snapshot)
    position = replace(base, is_sick=functools.cache(base.is_sick))
    is_free = functools.cache(freedays.is_free_day)
    cost_of = what_if(CURRENT_BASE)
    return {
        target.isoformat(): projection_dict(
            project(
                target, position, is_free=is_free, progress=progress, cost_of=cost_of
            )
        )
        for target in projection_targets(position.today)
    }
