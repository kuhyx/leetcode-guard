"""Everything the lock shows, as glyphs and numbers.

No Tk here. The whole surface is derived from a decision, a pool and a probe by
plain functions, so every mark the user will see is unit-testable without
opening a window.

**No words** (kuhy's textgate rule, 2026-11-08): the vocabulary is
:mod:`leetcode_guard._glyphs`. What a sentence used to explain now goes to the
log or to the status snapshot the phone app reads; the lock keeps the numbers.
State that a glyph alone would carry ambiguously is exposed as a field too
(``status_ok``, ``needed``) so the view can add a second channel (colour) and
tests can assert state rather than strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from leetcode_guard import _glyphs as g
from leetcode_guard._gate import GateDecision, GateState
from leetcode_guard._submissions import ProbeStatus
from leetcode_guard._viewmodel_lines import (
    ProblemLine,
    format_lines,
    note_easy_fallback,
    unit_problems,
)
from leetcode_guard._viewmodel_marks import accepted_prefix, notes_for
from leetcode_guard._viewmodel_phase import (
    NONE_SCREEN,
    PhaseScreen,
    build_phase_screen,
    review_line,
)

if TYPE_CHECKING:
    from datetime import datetime

    from leetcode_guard._pool_resolve import PoolResolution
    from leetcode_guard._submissions import SolveProbe
    from leetcode_guard._viewmodel_source import ViewSource


@dataclass(frozen=True)
class ViewModel:
    """The full content of the lock surface at one moment."""

    headline: str
    balance_line: str
    status_line: str
    notes: tuple[str, ...]
    problems: tuple[ProblemLine, ...]
    unlocked: bool
    show_escape: bool
    status_ok: bool = True
    """False when LeetCode cannot be checked: the status line turns red.

    A blind gate must never look like a watching one -- that is the
    "cannot check is not not-solved" rule, and a glyph swap alone is too
    quiet to carry it."""
    needed: int = 0
    screen: PhaseScreen = NONE_SCREEN
    """THEORY card, SOLVE bar or neither (``_viewmodel_phase``)."""


def build_problem_lines(
    pool: PoolResolution,
    *,
    limit: int,
    solved_slugs: frozenset[str] = frozenset(),
    unit: str = "",
    easy_only: bool = False,
) -> tuple[tuple[ProblemLine, ...], tuple[str, ...]]:
    """Format the suggestion list, minus anything solved since it was resolved.

    The pool is resolved once, before the window opens, and a lock that demands
    two solves therefore used to keep showing the first one after it had been
    accepted -- occupying a slot with a problem that could no longer help. The
    filter is applied here, on every repaint, rather than by re-resolving: the
    pool is ranked and live-verified deeper than it is displayed (see
    :data:`~leetcode_guard._constants.SUGGESTION_COUNT`), so the row that moves
    up into a freed slot was checked against LeetCode before the window opened.

    Args:
        pool: The resolved suggestion list, best first.
        limit: How many rows the surface has room for.
        solved_slugs: Everything now known to be solved, from the ledger and
            the latest probe together.
        unit: Narrow the list to this unit's problems (THEORY/SOLVE). A unit
            with nothing left to show falls back to the whole pool: an empty
            list would hide every Open button, the 2026-08-05 trap.
        easy_only: SOLVE(unit): only the unit's unsolved free Easy problems,
            no Medium, no Hard, no other unit's; fewer rows when fewer are
            left. An empty set falls back to ``unit``'s other problems and
            logs a warning.

    Returns:
        The lines to show, and the titles of the problems a solve removed from
        the window. The second element is what the surface acknowledges: a row
        that simply vanishes takes with it the only per-problem confirmation
        that the submission registered.
    """
    own = unit_problems(pool, unit, easy_only=easy_only)
    lines, dropped = format_lines(own, pool, limit, solved_slugs, narrowed=bool(unit))
    if easy_only and own is not pool.problems:
        note_easy_fallback(unit, empty=not lines)
        if not lines:
            # Today's list for the unit: a data race or a stale cache must
            # never take the Open buttons away (the 2026-08-05 rule).
            own = unit_problems(pool, unit)
            lines, dropped = format_lines(own, pool, limit, solved_slugs, narrowed=True)
    if lines or own is pool.problems:
        return lines, dropped
    return format_lines(pool.problems, pool, limit, solved_slugs, narrowed=False)


def lock_rows(
    source: ViewSource,
) -> tuple[PhaseScreen, tuple[ProblemLine, ...], tuple[str, ...]]:
    """The screen and its rows, in order; the one path the lock and the snapshot share.

    Returns:
        The phase screen, the rows (one review row in place of the SOLVE rows
        when cards are due), and the titles a solve removed.
    """
    screen = build_phase_screen(source.phase, source.review)
    problems, dropped = build_problem_lines(
        source.pool,
        limit=source.limit,
        solved_slugs=source.solved_slugs,
        unit=screen.unit if screen.unit_list else "",
        easy_only=screen.easy_only,
    )
    if screen.review is not None:
        # Review first: one row in place of the SOLVE rows. ``dropped`` stays,
        # so a solve landing now is still acknowledged on the status line.
        problems = (review_line(screen.review),)
    return screen, problems, dropped


_FREE_DAY_MARKS: Final = {
    GateState.UNLOCKED_NOT_STARTED: g.NOT_STARTED,
    GateState.UNLOCKED_SICK_DAY: g.SICK,
    GateState.UNLOCKED_FOCUS_DAY: g.FOCUS,
}


def _headline(decision: GateDecision) -> str:
    """The single biggest mark on the screen, beside the drawn padlock.

    Locked: one hollow circle per accepted submission still owed. A free day
    names *which* free day by its own glyph, so the stood-down gate never reads
    as "unlocked by credit".
    """
    if (mark := _FREE_DAY_MARKS.get(decision.state)) is not None:
        return mark
    if not decision.locked:
        return g.SOLVED
    if decision.state is GateState.LOCKED_CLOCK_UNTRUSTED:
        return g.CLOCK_BACK
    return g.dots(decision.needed)


def _remaining_after_today(decision: GateDecision) -> int:
    """Credits left once today is paid for.

    ``decide`` is pure, so a freshly minted charge has not been added to the
    ledger yet and ``balance.available`` is still the *pre-charge* figure.
    Showing it verbatim told the user they had one more credit than they did,
    every single time the gate charged a day.
    """
    if decision.state is GateState.UNLOCKED_CHARGED_NOW:
        return decision.balance.available - decision.cost
    return decision.balance.available


def _balance_line(decision: GateDecision) -> str:
    """``◆ 0  │  ☀ 2 (1+1▼)  │  ▼ 7``: credits, today's price, debt.

    The surcharge stays spelled out as numbers, because a quota that silently
    doubled reads as a bug.
    """
    cost = decision.cost
    surcharge = min(decision.debt.surcharge_on(decision.day), cost)
    today = f"{g.TODAY} {cost}"
    if surcharge:
        today = f"{today} ({cost - surcharge}+{surcharge}{g.DEBT})"
    parts = [f"{g.CREDIT} {_remaining_after_today(decision)}", today]
    if decision.debt.outstanding:
        parts.append(f"{g.DEBT} {decision.debt.outstanding}")
    return g.SEP.join(parts)


def _status_line(probe: SolveProbe, *, checked_at: datetime) -> str:
    """What the poller last saw, and when.

    An unverifiable probe gets its own glyph *and* (in the view) the danger
    colour. It must never render like a watching one, which would leave the
    user with no idea the gate is blind; the reason goes to the log.
    """
    stamp = checked_at.strftime("%H:%M:%S")
    if probe.status is ProbeStatus.UNVERIFIABLE:
        return f"{g.BLIND} {stamp}"
    return f"{g.WATCHING} {stamp}"


def build_viewmodel(
    decision: GateDecision,
    source: ViewSource,
    probe: SolveProbe,
    *,
    checked_at: datetime,
    show_escape: bool = False,
) -> ViewModel:
    """Assemble the whole surface.

    Args:
        decision: The gate verdict.
        source: The resolved pool, the auth state and the display limit; see
            :class:`~leetcode_guard._viewmodel_source.ViewSource`.
        probe: The most recent solve check.
        checked_at: When that check happened, for the status line.
        show_escape: Whether the escape hatch button is currently offered.

    Returns:
        The rendered marks.
    """
    screen, problems, dropped = lock_rows(source)
    return ViewModel(
        headline=_headline(decision),
        balance_line=_balance_line(decision),
        status_line=accepted_prefix(dropped)
        + _status_line(probe, checked_at=checked_at),
        notes=notes_for(decision, source),
        problems=problems,
        unlocked=not decision.locked,
        show_escape=show_escape,
        status_ok=probe.status is not ProbeStatus.UNVERIFIABLE,
        needed=decision.needed,
        screen=screen,
    )
