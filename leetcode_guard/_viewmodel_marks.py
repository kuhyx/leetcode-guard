"""The lock's smaller marks: acknowledged solves and warning notes.

Split out of ``_viewmodel.py`` for the 250-line cap. Pure, no Tk, glyphs only
(:mod:`leetcode_guard._glyphs`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from leetcode_guard import _glyphs as g

if TYPE_CHECKING:
    from leetcode_guard._gate import GateDecision
    from leetcode_guard._viewmodel_source import ViewSource

ACCEPTED_NAMES: Final = 2
"""How many solved problems the status line names before it starts counting.

Bounded because the acknowledgement persists for the rest of the lock and
problem titles run to fifty characters ("Minimum Operations to Make Array Sum
Divisible by K"). A day eight credits deep into debt would otherwise grow a
status line wider than the screen -- and the lock surface is a ``place``-centred
frame, which shears off *both* edges when it overflows rather than clipping one.
"""


def accepted_prefix(dropped: tuple[str, ...]) -> str:
    """Credit the solves that just emptied a row, or say nothing.

    The row itself vanishes immediately -- the slot is the scarce thing -- so
    the confirmation moves here, where it costs no space. It keeps showing for
    the rest of the lock, because the solved set only grows and an
    acknowledgement that expires after one tick is one the user can miss
    entirely while looking at the browser. What is still owed is the
    headline's circles.
    """
    if not dropped:
        return ""
    named = ", ".join(dropped[:ACCEPTED_NAMES])
    if len(dropped) > ACCEPTED_NAMES:
        named = f"{named} +{len(dropped) - ACCEPTED_NAMES}"
    return f"{g.SOLVED} {named}{g.SEP}"


def notes_for(decision: GateDecision, source: ViewSource) -> tuple[str, ...]:
    """Small warning marks; the pool's explanations live in the snapshot.

    Only what changes what the user should trust stays on the lock: an
    unfiltered list (no LeetCode session), refused credits, an unreadable
    ledger key.
    """
    notes: list[str] = []
    if not source.auth.present:
        notes.append(g.SIGNED_OUT)
    if not decision.balance.integrity_ok:
        notes.append(g.UNSIGNED)
    if decision.balance.discounted:
        notes.append(f"{g.REFUSED} {decision.balance.discounted}")
    return tuple(notes)
