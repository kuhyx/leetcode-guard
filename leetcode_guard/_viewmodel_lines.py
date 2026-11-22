"""One suggestion row as data, and the loop that formats a pool into rows.

Split from ``_viewmodel.py`` for the 250-line cap when the unit screens
(``_viewmodel_phase``) narrowed the list to one unit. No Tk, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard import _glyphs as g

if TYPE_CHECKING:
    from leetcode_guard._pool_resolve import PoolResolution
    from leetcode_guard._problem import Problem

_logger: Final = logging.getLogger(__name__)

WARNED: Final[set[str]] = set()
"""Units whose "no Easy left" fallback is already logged. A repaint runs every
poll, so one stale cache would otherwise log once a second; a refilled set
takes the unit out again (:func:`note_easy_fallback`)."""


@dataclass(frozen=True)
class ProblemLine:
    """One suggested problem, ready to render."""

    label: str
    """Row number and the problem's title (LeetCode's content)."""
    url: str
    slug: str = ""
    """Which problem this is, so rows revealed by scrolling can be verified."""
    mark: str = ""
    """Credit weight and acceptance rate: ``◆◆  48%``."""
    difficulty: str = ""
    """``Easy``/``Medium``/``Hard``: picks the mark's colour, never painted."""


def unit_problems(
    pool: PoolResolution, unit: str, *, easy_only: bool = False
) -> tuple[Problem, ...]:
    """``unit``'s problems in pool order; the whole pool without a unit.

    ``easy_only`` (SOLVE) keeps the free Easy ones: the phase machine finishes
    a unit on exactly that set (``_phase_inputs.easy_by_unit``).
    """
    blocks = pool.blocks
    if not unit or blocks is None:
        return pool.problems
    return tuple(
        p
        for p in pool.problems
        if blocks.unit_id(p) == unit
        and (not easy_only or (p.difficulty == "Easy" and not p.paid_only))
    )


def note_easy_fallback(unit: str, *, empty: bool) -> None:
    """Log once per unit that SOLVE had no Easy row; a refill re-arms it."""
    if not empty:
        WARNED.discard(unit)
    elif unit not in WARNED:
        WARNED.add(unit)
        _logger.warning(
            "%s is in SOLVE but has no unsolved free Easy row: "
            "showing the unit's other problems",
            unit,
        )


def format_lines(
    problems: tuple[Problem, ...],
    pool: PoolResolution,
    limit: int,
    solved_slugs: frozenset[str],
    *,
    narrowed: bool,
) -> tuple[tuple[ProblemLine, ...], tuple[str, ...]]:
    """One line per unsolved problem, up to ``limit``; the solved ones' titles.

    A narrowed list drops the pencil: every row of a THEORY unit would carry
    it, and the card above already says it once.
    """
    lines: list[ProblemLine] = []
    dropped: list[str] = []
    blocks = None if narrowed else pool.blocks
    for problem in problems:
        if len(lines) == limit:
            break
        if problem.title_slug in solved_slugs:
            dropped.append(problem.title)
            continue
        lines.append(
            ProblemLine(
                label=f"{len(lines) + 1}  {problem.title}",
                url=problem.url,
                slug=problem.title_slug,
                mark=g.problem_mark(
                    problem.difficulty,
                    problem.ac_rate,
                    waits=blocks is not None and blocks.waits(problem),
                ),
                difficulty=problem.difficulty,
            )
        )
    return tuple(lines), tuple(dropped)
