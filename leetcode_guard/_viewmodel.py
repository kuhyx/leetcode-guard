"""Everything the lock says, as pure text.

No Tk here. The whole surface is derived from a decision, a pool and a probe by
plain functions, so every sentence the user will read is unit-testable without
opening a window.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from leetcode_guard._debt import cost_phrase, debt_line
from leetcode_guard._gate import GateDecision, GateState
from leetcode_guard._submissions import ProbeStatus

if TYPE_CHECKING:
    from datetime import datetime

    from leetcode_guard._auth import AuthState
    from leetcode_guard._pool_resolve import PoolResolution
    from leetcode_guard._submissions import SolveProbe


@dataclass(frozen=True)
class ProblemLine:
    """One suggested problem, ready to render."""

    label: str
    url: str


@dataclass(frozen=True)
class ViewModel:
    """The full text of the lock surface at one moment."""

    headline: str
    balance_line: str
    status_line: str
    notes: tuple[str, ...]
    problems: tuple[ProblemLine, ...]
    unlocked: bool
    show_escape: bool


def build_problem_lines(
    pool: PoolResolution,
    *,
    limit: int,
    solved_slugs: frozenset[str] = frozenset(),
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

    Returns:
        The lines to show, and the titles of the problems a solve removed from
        the window. The second element is what the surface acknowledges: a row
        that simply vanishes takes with it the only per-problem confirmation
        that the submission registered.
    """
    lines: list[ProblemLine] = []
    dropped: list[str] = []
    for problem in pool.problems:
        if len(lines) == limit:
            break
        if problem.title_slug in solved_slugs:
            dropped.append(problem.title)
            continue
        lines.append(
            ProblemLine(
                label=(
                    f"{len(lines) + 1}. {problem.title}  --  {problem.difficulty}, "
                    f"{problem.ac_rate:.1f}% acceptance"
                ),
                url=problem.url,
            )
        )
    return tuple(lines), tuple(dropped)


def _headline(decision: GateDecision) -> str:
    """The single biggest line on the screen."""
    if decision.state is GateState.UNLOCKED_NOT_STARTED:
        # Without its own branch this fell through to "Unlocked -- 0 credits
        # left", which is technically true and tells the reader nothing about
        # why the gate is not doing anything.
        return "Not in force yet"
    if not decision.locked:
        left = _remaining_after_today(decision)
        plural = "" if left == 1 else "s"
        return f"Unlocked -- {left} credit{plural} left"
    if decision.state is GateState.LOCKED_CLOCK_UNTRUSTED:
        return "Locked -- the system clock moved backwards"
    plural = "" if decision.needed == 1 else "s"
    return f"Solve {decision.needed} LeetCode problem{plural} to unlock"


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
    """Where the credits stand, and what today costs."""
    costs = cost_phrase(decision.day, decision.cost, decision.debt)
    base = f"Credits {_remaining_after_today(decision)}  |  {costs}"
    if decision.needed:
        return f"{base}  |  need {decision.needed} more"
    return base


def _status_line(probe: SolveProbe, *, checked_at: datetime) -> str:
    """What the poller last saw.

    An unverifiable probe says so in as many words. It must never render as
    "not solved yet", which is the same sentence a *working* check would
    produce and would leave the user with no idea the gate is blind.
    """
    stamp = checked_at.strftime("%H:%M:%S")
    if probe.status is ProbeStatus.UNVERIFIABLE:
        return f"Cannot check LeetCode ({probe.reason}) -- last tried {stamp}"
    return f"Watching for an accepted submission... last checked {stamp}"


ACCEPTED_NAMES: Final = 2
"""How many solved problems the status line names before it starts counting.

Bounded because the acknowledgement persists for the rest of the lock and
problem titles run to fifty characters ("Minimum Operations to Make Array Sum
Divisible by K"). A day eight credits deep into debt would otherwise grow a
status line wider than the screen -- and the lock surface is a ``place``-centred
frame, which shears off *both* edges when it overflows rather than clipping one.
"""


def _accepted_prefix(dropped: tuple[str, ...], *, needed: int) -> str:
    """Credit the solves that just emptied a row, or say nothing.

    The row itself vanishes immediately -- the slot is the scarce thing -- so
    the confirmation moves here, where it costs no space. It keeps saying so
    for the rest of the lock, because the solved set only grows and an
    acknowledgement that expires after one tick is one the user can miss
    entirely while looking at the browser.
    """
    if not dropped:
        return ""
    named = ", ".join(dropped[:ACCEPTED_NAMES])
    if len(dropped) > ACCEPTED_NAMES:
        named = f"{named} and {len(dropped) - ACCEPTED_NAMES} more"
    accepted = f"Accepted: {named}"
    if needed:
        plural = "" if needed == 1 else "s"
        return f"{accepted} -- need {needed} more solve{plural}  |  "
    return f"{accepted}  |  "


def build_viewmodel(
    decision: GateDecision,
    pool: PoolResolution,
    auth: AuthState,
    probe: SolveProbe,
    *,
    checked_at: datetime,
    limit: int,
    show_escape: bool = False,
    solved_slugs: frozenset[str] = frozenset(),
) -> ViewModel:
    """Assemble the whole surface.

    Args:
        decision: The gate verdict.
        pool: The resolved suggestion list, including its provenance notes.
        auth: Whether solved problems could be filtered out.
        probe: The most recent solve check.
        checked_at: When that check happened, for the status line.
        limit: How many problems to list.
        show_escape: Whether the escape hatch button is currently offered.
        solved_slugs: Everything now known to be solved. Unlike ``pool``, which
            is resolved once before the window opens, this is recomputed every
            tick, so a problem solved *during* the lock stops being suggested.

    Returns:
        The rendered text.
    """
    notes = list(pool.notes)
    if auth.note not in notes:
        notes.insert(0, auth.note)
    if decision.state in {
        GateState.LOCKED_CLOCK_UNTRUSTED,
        GateState.UNLOCKED_NOT_STARTED,
    }:
        notes.append(decision.reason)
    if not decision.balance.integrity_ok:
        notes.append(
            "The ledger integrity key is unreadable, so signatures are not "
            "being checked."
        )
    if decision.balance.discounted:
        notes.append(
            f"{decision.balance.discounted} ledger credits were refused "
            "(bad signature, or written by another device)."
        )
    if decision.debt.outstanding:
        notes.append(debt_line(decision.debt))

    problems, dropped = build_problem_lines(
        pool, limit=limit, solved_slugs=solved_slugs
    )
    prefix = _accepted_prefix(dropped, needed=decision.needed)

    return ViewModel(
        headline=_headline(decision),
        balance_line=_balance_line(decision),
        status_line=prefix + _status_line(probe, checked_at=checked_at),
        notes=tuple(notes),
        problems=problems,
        unlocked=not decision.locked,
        show_escape=show_escape,
    )
