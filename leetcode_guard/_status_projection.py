"""Assemble a projection from the gate snapshot, for the CLI and the window.

The one place that knows how to go from "what is on disk" plus the typed
inputs -- a date, a base price, per-difficulty goals -- to the lines both
surfaces print. Tk-free, so ``--status --by`` never imports a widget, and
network-free except for :func:`fetch_live_progress`, which is the single call
either surface makes and which both label as such.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import logging
from typing import TYPE_CHECKING, Final

import freedays

from leetcode_guard._constants import PROGRESS_CACHE_FILE
from leetcode_guard._daycost import CURRENT_PRICING, local_today, parse_day, what_if
from leetcode_guard._progress import (
    DIFFICULTIES,
    read_progress_cache,
    refresh_progress,
)
from leetcode_guard._projection import (
    Position,
    default_target,
    format_target,
    parse_target,
    project,
)
from leetcode_guard._projection_text import progress_lines, projection_lines
from leetcode_guard._scenario import MIN_PRICE, Goal, Scenario, build_scenario
from leetcode_guard._scenario_text import prices_line, scenario_lines
from leetcode_guard._settings import build_client

if TYPE_CHECKING:
    from datetime import date

    from leetcode_guard._progress import Progress
    from leetcode_guard._projection import Projection
    from leetcode_guard._status import StatusSnapshot

_logger: Final = logging.getLogger(__name__)

PAST_TARGET: Final = "That date is already behind you -- pick today or later."
UNREADABLE_TARGET: Final = "Not a date. Use dd.mm.yyyy, e.g. 31.12.2026."
BAD_PRICE: Final = f"Price must be a whole number of credits, {MIN_PRICE} or more."
GOAL_NEEDS_COUNTS: Final = "A goal needs the solved counts above."


def unknown_difficulty(name: str) -> str:
    """The message for a goal keyed on something LeetCode does not grade."""
    return f"No such difficulty {name!r}; use {', '.join(DIFFICULTIES)}."


def bad_goal(name: str) -> str:
    """The message for a goal entry that is not a count."""
    return f"The {name} goal must be a whole number, or blank."


@dataclass(frozen=True)
class ProjectionInputs:
    """The three controls' text, owned by the caller across repaints.

    Attributes:
        target_text: The date entry, ``dd.mm.yyyy``.
        price_text: The Tue-Thu base price entry.
        goal_texts: Per-difficulty goal entries; blank means no goal.
    """

    target_text: str
    price_text: str = str(CURRENT_PRICING.base_cost)
    goal_texts: dict[str, str] = field(default_factory=dict)

    @classmethod
    def default(cls, today: date) -> ProjectionInputs:
        """End of this year, at the live price, no goal."""
        return cls(target_text=format_target(default_target(today)))

    def price(self) -> int | None:
        """The base price, or ``None`` when the entry is not one."""
        text = self.price_text.strip()
        if not text.isdigit() or int(text) < MIN_PRICE:
            return None
        return int(text)

    def goal(self) -> Goal | str | None:
        """The goal, ``None`` when every entry is blank, or the complaint."""
        counts: dict[str, int] = {}
        for name, text in self.goal_texts.items():
            cleaned = text.strip()
            if not cleaned:
                continue
            if name not in DIFFICULTIES:
                return unknown_difficulty(name)
            if not cleaned.isdigit():
                return bad_goal(name)
            counts[name] = int(cleaned)
        return Goal(counts) if counts else None


@dataclass(frozen=True)
class ProjectionReport:
    """What the surface shows: the position now, then the position on the date.

    ``projection`` is ``None`` with ``problem`` set when the target could not
    be used; the progress lines are still worth showing then.
    """

    progress: Progress | None
    projection: Projection | None
    problem: str | None = None
    base_cost: int | None = None
    scenario: Scenario | None = None
    goal: Goal | None = None
    goal_problem: str | None = None

    def now_lines(self) -> list[str]:
        """Solved / total per difficulty, today."""
        return progress_lines(self.progress)

    def then_lines(self) -> list[str]:
        """The working and the counts on the target date, or why not."""
        if self.projection is None or self.base_cost is None:
            return [self.problem or UNREADABLE_TARGET]
        return [
            prices_line(self.base_cost),
            *projection_lines(self.projection, self.progress),
        ]

    def goal_lines(self) -> list[str]:
        """The what-if for the goal, the complaint, or nothing when none was set."""
        if self.goal_problem is not None:
            return [self.goal_problem]
        if self.scenario is None or self.goal is None or self.progress is None:
            return []
        return scenario_lines(self.scenario, self.goal, self.progress)


def position_of(snapshot: StatusSnapshot) -> Position:
    """Lift the four facts the projection needs off a gate snapshot.

    ``snapshot.day`` is the ISO day the gate decided for; falling back to the
    local date covers a snapshot built from a malformed one, which the status
    code already logs.
    """
    day = parse_day(snapshot.day) or local_today()
    return Position(
        today=day,
        charged_today=snapshot.charged_today,
        available=snapshot.available,
        debt_outstanding=snapshot.debt_outstanding,
    )


def build_report(
    snapshot: StatusSnapshot, progress: Progress | None, inputs: ProjectionInputs
) -> ProjectionReport:
    """Parse the inputs, project, and work the goal. Never raises on user input."""
    target = parse_target(inputs.target_text)
    if target is None:
        return ProjectionReport(progress, None, UNREADABLE_TARGET)
    position = position_of(snapshot)
    if target < position.today:
        return ProjectionReport(progress, None, PAST_TARGET)
    price = inputs.price()
    if price is None:
        return ProjectionReport(progress, None, BAD_PRICE)
    projection = project(
        target,
        position,
        is_free=_is_free_day,
        progress=progress,
        cost_of=what_if(price),
    )
    return _with_goal(progress, projection, price, inputs)


def _with_goal(
    progress: Progress | None,
    projection: Projection,
    price: int,
    inputs: ProjectionInputs,
) -> ProjectionReport:
    """Attach the what-if for the goal, or the reason there is none."""
    goal = inputs.goal()
    if isinstance(goal, str):
        return ProjectionReport(
            progress, projection, base_cost=price, goal_problem=goal
        )
    if goal is None:
        return ProjectionReport(progress, projection, base_cost=price)
    if progress is None:
        return ProjectionReport(
            progress, projection, base_cost=price, goal_problem=GOAL_NEEDS_COUNTS
        )
    scenario = build_scenario(price, goal, progress, projection, is_free=_is_free_day)
    return ProjectionReport(
        progress, projection, base_cost=price, scenario=scenario, goal=goal
    )


def _is_free_day(day: date) -> bool:
    """The shared free-day pool, positionally -- what ``project`` expects."""
    return freedays.is_free_day(day)


def cached_progress() -> Progress | None:
    """Whatever the last fetch mirrored, or ``None``. Reads one file."""
    return read_progress_cache(PROGRESS_CACHE_FILE)


def fetch_live_progress() -> Progress | None:
    """The one network call: refresh the mirror, falling back to it on failure.

    Builds its own client because the callers -- the status window and
    ``--status --by`` -- are the surfaces that otherwise never touch the
    network, so none of them has one to hand.
    """
    client = build_client()
    now = datetime.now(tz=UTC).timestamp()
    progress = refresh_progress(
        client.post, client.username, PROGRESS_CACHE_FILE, now=now
    )
    if progress is None:
        _logger.warning("no solve progress available, live or cached")
    return progress
