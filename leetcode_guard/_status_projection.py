"""Assemble a projection from the gate snapshot, for the CLI and the window.

The one place that knows how to go from "what is on disk" plus "a date" to
the lines both surfaces print. Tk-free, so ``--status --by`` never imports a
widget, and network-free except for :func:`fetch_live_progress`, which is the
single call either surface makes and which both label as such.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from typing import TYPE_CHECKING, Final

import freedays

from leetcode_guard._constants import PROGRESS_CACHE_FILE
from leetcode_guard._daycost import local_today, parse_day
from leetcode_guard._progress import read_progress_cache, refresh_progress
from leetcode_guard._projection import Position, parse_target, project
from leetcode_guard._projection_text import progress_lines, projection_lines
from leetcode_guard._settings import build_client

if TYPE_CHECKING:
    from datetime import date

    from leetcode_guard._progress import Progress
    from leetcode_guard._projection import Projection
    from leetcode_guard._status import StatusSnapshot

_logger: Final = logging.getLogger(__name__)

PAST_TARGET: Final = "That date is already behind you -- pick today or later."
UNREADABLE_TARGET: Final = "Not a date. Use dd.mm.yyyy, e.g. 31.12.2026."


@dataclass(frozen=True)
class ProjectionReport:
    """What the surface shows: the position now, then the position on the date.

    ``projection`` is ``None`` with ``problem`` set when the target could not
    be used; the progress lines are still worth showing then.
    """

    progress: Progress | None
    projection: Projection | None
    problem: str | None = None

    def now_lines(self) -> list[str]:
        """Solved / total per difficulty, today."""
        return progress_lines(self.progress)

    def then_lines(self) -> list[str]:
        """The working and the counts on the target date, or why not."""
        if self.projection is None:
            return [self.problem or UNREADABLE_TARGET]
        return projection_lines(self.projection, self.progress)


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
    snapshot: StatusSnapshot, progress: Progress | None, target_text: str
) -> ProjectionReport:
    """Parse the date and project. Never raises on user input."""
    target = parse_target(target_text)
    if target is None:
        return ProjectionReport(progress, None, UNREADABLE_TARGET)
    position = position_of(snapshot)
    if target < position.today:
        return ProjectionReport(progress, None, PAST_TARGET)
    projection = project(target, position, is_free=_is_free_day, progress=progress)
    return ProjectionReport(progress, projection)


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
