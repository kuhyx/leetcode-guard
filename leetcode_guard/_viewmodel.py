"""Everything the lock says, as pure text.

No Tk here. The whole surface is derived from a decision, a pool and a probe by
plain functions, so every sentence the user will read is unit-testable without
opening a window.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from leetcode_guard._daycost import weekday_name
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


def build_problem_lines(pool: PoolResolution, *, limit: int) -> tuple[ProblemLine, ...]:
    """Format the suggestion list."""
    return tuple(
        ProblemLine(
            label=(
                f"{index}. {problem.title}  --  {problem.difficulty}, "
                f"{problem.ac_rate:.1f}% acceptance"
            ),
            url=problem.url,
        )
        for index, problem in enumerate(pool.problems[:limit], start=1)
    )


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
    day = weekday_name(decision.day)
    base = f"Credits {_remaining_after_today(decision)}  |  {day} costs {decision.cost}"
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


def build_viewmodel(
    decision: GateDecision,
    pool: PoolResolution,
    auth: AuthState,
    probe: SolveProbe,
    *,
    checked_at: datetime,
    limit: int,
    show_escape: bool = False,
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

    return ViewModel(
        headline=_headline(decision),
        balance_line=_balance_line(decision),
        status_line=_status_line(probe, checked_at=checked_at),
        notes=tuple(notes),
        problems=build_problem_lines(pool, limit=limit),
        unlocked=not decision.locked,
        show_escape=show_escape,
    )
