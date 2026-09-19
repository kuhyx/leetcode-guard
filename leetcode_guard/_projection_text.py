"""The projection as lines of text, shared by the CLI and the status window.

One formatter so ``--status --by`` and the window can never disagree about a
number: the window draws these lines one label each, the CLI prints them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from leetcode_guard._progress import DIFFICULTIES
from leetcode_guard._projection import format_target, percent

if TYPE_CHECKING:
    from leetcode_guard._progress import Progress
    from leetcode_guard._projection import Projection

_ALL: Final = "All"
_LABEL_WIDTH: Final = 7
"""Wide enough for ``Medium`` plus a space, so the columns line up in a
monospace caption."""

UNKNOWN_PROGRESS: Final = (
    "Solved counts unknown -- LeetCode could not be reached and nothing is cached."
)


def is_count_line(line: str) -> bool:
    """Whether ``line`` is one of the aligned count rows.

    The window sets those in a monospace face so the columns line up; the
    CLI does not care.
    """
    return line.startswith((*DIFFICULTIES, _ALL))


def _count_line(label: str, solved: int, total: int) -> str:
    """``Easy     55 /  965   (5.7 %)   910 left``."""
    share = percent(solved, total)
    return (
        f"{label:<{_LABEL_WIDTH}}{solved:>5} / {total:<5} ({share:5.1f} %)"
        f"{max(0, total - solved):>6} left"
    )


def _fetched_phrase(fetched_at: float) -> str:
    """``as of 2026-09-19 15:31`` in local time."""
    stamp = datetime.fromtimestamp(fetched_at, tz=UTC).astimezone()
    return f"as of {stamp:%Y-%m-%d %H:%M}"


def progress_lines(progress: Progress | None) -> list[str]:
    """Where you stand now, per difficulty and overall."""
    if progress is None:
        return [UNKNOWN_PROGRESS]
    lines = [
        _count_line(name, progress.solved[name], progress.total[name])
        for name in DIFFICULTIES
    ]
    lines.append(_count_line(_ALL, progress.solved_all, progress.total_all))
    lines.append(f"LeetCode profile figures, {_fetched_phrase(progress.fetched_at)}.")
    return lines


def _rules_line(projection: Projection) -> str:
    """What the mechanism would have collected on its own by then."""
    if projection.debt_left_by_rules == 0:
        return (
            f"The rules alone demand the same {projection.rules_demand} by then "
            "(debt fully repaid at 1 per day)."
        )
    return (
        f"The rules alone would demand {projection.rules_demand} by then and "
        f"leave {projection.debt_left_by_rules} of the debt still owed -- "
        "the figure above clears it too."
    )


def projection_lines(projection: Projection, progress: Progress | None) -> list[str]:
    """The target, the working, and the position on that date."""
    span = (
        f"By {format_target(projection.target)}, counting from "
        f"{format_target(projection.first_day)}: {projection.gated_days} gated "
        f"day(s), {projection.free_days} free."
    )
    working = (
        f"{projection.base_cost} (day prices) + {projection.debt} (debt) - "
        f"{projection.available} (banked) = {projection.required} new problem(s) "
        "to solve."
    )
    lines = [span, working, _rules_line(projection)]
    if projection.projected is None or progress is None:
        lines.append("Per-difficulty projection needs the solved counts above.")
        return lines
    lines.extend(
        _count_line(name, projection.projected[name], progress.total[name])
        for name in DIFFICULTIES
    )
    solved_all = sum(projection.projected[name] for name in DIFFICULTIES)
    lines.append(_count_line(_ALL, solved_all, progress.total_all))
    lines.append(
        "Assumes every new solve is a problem not solved before, served Easy "
        "first, then Medium, then Hard -- the suggestion order."
    )
    return lines
