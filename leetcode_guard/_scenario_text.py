"""The what-if as lines of text, shared by the CLI and the status window.

Same contract as ``_projection_text``: one formatter, so the two surfaces can
never disagree about a number.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._daycost import CURRENT_PRICING
from leetcode_guard._progress import DIFFICULTIES
from leetcode_guard._projection import format_target

if TYPE_CHECKING:
    from datetime import date

    from leetcode_guard._progress import Progress
    from leetcode_guard._scenario import Goal, Scenario

BEYOND_EASY_NOTE = (
    "The goal sums each difficulty's shortfall -- it is yours to pick which. The "
    "rows above fill Easy first, so they show Medium and Hard moving only once "
    "Easy is exhausted."
)
NO_PRICED_DAY = (
    "No priced day lies between now and that date, so no price can land the goal."
)


def prices_line(base_cost: int) -> str:
    """``Prices: Tue/Wed/Thu cost 2, Mon/Fri/Sat/Sun cost 4.``."""
    return f"Prices: {CURRENT_PRICING.with_base(base_cost).describe()}."


def goal_line(goal: Goal, progress: Progress) -> str:
    """``Goal: Easy 837 (779 more), Medium 100 (100 more).``."""
    parts = [
        f"{name} {count} ({max(0, count - progress.solved[name])} more)"
        for name in DIFFICULTIES
        if (count := goal.counts.get(name)) is not None
    ]
    return f"Goal: {', '.join(parts)}."


def _when(day: date | None) -> str:
    return "never within the horizon" if day is None else f"on {format_target(day)}"


def _typed_price_line(scenario: Scenario) -> str:
    """What the typed price does to the goal by the target."""
    by = format_target(scenario.target)
    if scenario.needed == 0:
        return "The goal is already reached."
    if scenario.shortfall == 0:
        return (
            f"At price {scenario.base_cost}: {scenario.forced} forced by {by}, "
            f"the goal needs {scenario.needed} -- reached {_when(scenario.lands_on)}."
        )
    return (
        f"At price {scenario.base_cost}: {scenario.forced} forced by {by}, "
        f"{scenario.shortfall} short of the {scenario.needed} the goal needs -- "
        f"reached {_when(scenario.lands_on)}."
    )


def _minimal_price_line(scenario: Scenario) -> str:
    """The answer to "by how much": the exact price and its whole-number ceiling."""
    if scenario.exact_price is None:
        return NO_PRICED_DAY
    exact = f"{float(scenario.exact_price):.2f}"
    by = format_target(scenario.target)
    return (
        f"Price that lands the goal exactly on {by}: {exact}; "
        f"smallest whole price {scenario.minimal_price}, which lands it "
        f"{_when(scenario.minimal_lands_on)}."
    )


def scenario_lines(scenario: Scenario, goal: Goal, progress: Progress) -> list[str]:
    """The goal, what the typed price does to it, and the price that makes it."""
    lines = [goal_line(goal, progress)]
    beyond = [
        f"{name} {goal.counts[name]} exceeds the {progress.total[name]} on the site."
        for name in goal.unreachable(progress)
    ]
    if beyond:
        return lines + beyond
    lines.append(_typed_price_line(scenario))
    if scenario.needed:
        lines.append(_minimal_price_line(scenario))
    if goal.beyond_easy():
        lines.append(BEYOND_EASY_NOTE)
    return lines
