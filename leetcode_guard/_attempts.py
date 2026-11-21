"""How long one solve really took, from heartbeats and the ledger's credit.

Display-only, like ``attempts.json`` itself: read-only over the ledger and the
attempt store, and **nothing that decides, charges or credits may import it**
(``test_display_only_imports`` bans it, transitively). The purpose is review,
not enforcement: a solve that took over 20 minutes of active time although the
unit's theory was already taught is worth a second look.

Definitions, all pure:

* A **solve** is the EARLIEST credit of a slug; its accept time ``T`` is the
  credit's ``submitted_at``. Later credits of the slug are repeats.
* Its **window** is every beat and submission of that slug, from every day
  record, at or before ``T`` (an attempt may span days).
* **Active time** sums the gaps between neighbouring beats, closed by ``T``,
  that are at most :data:`GAP_SECONDS`. Beats come a minute apart while a tab
  is visible, so a longer gap means the problem was not on screen.
* A solve with no beat in its window is **unknown**: never measured, never
  flagged, never counted in a share.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING, Final

from leetcode_guard._attempt_model import TABS, Beat, day_of
from leetcode_guard._ledger import CREDIT

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from collections.abc import Set as AbstractSet

    from leetcode_guard._attempt_model import AttemptRecord
    from leetcode_guard._ledger_io import Ledger

FLAG_SECONDS: Final = 20 * 60
"""Active time above this, with the theory taught, flags the solve."""
FAST_SECONDS: Final = 10 * 60
"""Active time below this counts as a fast solve in the share."""
GAP_SECONDS: Final = 5 * 60
"""A beat-to-beat gap longer than this is not active time."""
WINDOW_DAYS: Final = 28
"""How far back the report's ``measured`` list and share look."""
ACCEPTED: Final = "Accepted"
THEORY_DONE: Final = "done"
THEORY_UNKNOWN: Final = "unknown"


@dataclass(frozen=True)
class Credit:
    """One accepted submission as the ledger recorded it."""

    slug: str
    accepted_at: int
    """Unix seconds (the credit's ``submitted_at``)."""


@dataclass(frozen=True)
class Solve:
    """The measurement of one solve; the fields of a report row."""

    slug: str
    accepted_at: int
    measured: bool
    active_seconds: int
    span_seconds: int | None
    tab_seconds: dict[str, int]
    failed: dict[str, int]
    first_submission_active_seconds: int
    theory: str
    flagged: bool


def credits_of(ledger: Ledger) -> list[Credit]:
    """The credit rows that name a slug and carry a numeric ``submitted_at``."""
    found: list[Credit] = []
    for entry in ledger.of_kind(CREDIT):
        slug = entry.detail.get("title_slug")
        stamp = entry.detail.get("submitted_at", "")
        if slug and stamp.isdecimal():
            found.append(Credit(slug, int(stamp)))
    return found


def first_credits(earned: Iterable[Credit]) -> list[Credit]:
    """One credit per slug, the earliest; the rest are repeats of a known problem."""
    earliest: dict[str, Credit] = {}
    for credit in earned:
        known = earliest.get(credit.slug)
        if known is None or credit.accepted_at < known.accepted_at:
            earliest[credit.slug] = credit
    return list(earliest.values())


def active_seconds(beats: Iterable[int], end: int) -> int:
    """Sum the gaps of at most :data:`GAP_SECONDS` between beats closed by ``end``."""
    times = [*sorted(beats), end]
    return sum(
        later - earlier
        for earlier, later in pairwise(times)
        if later - earlier <= GAP_SECONDS
    )


def _tab_seconds(beats: Sequence[Beat], end: int) -> dict[str, int]:
    """Each counted gap goes to the tab of the beat that starts it."""
    tabs = dict.fromkeys(TABS, 0)
    ordered = sorted(beats, key=lambda beat: beat.at)
    ends = [beat.at for beat in ordered] + [end]
    for beat, later in zip(ordered, ends[1:], strict=True):
        if later - beat.at <= GAP_SECONDS and beat.tab in tabs:
            tabs[beat.tab] += later - beat.at
    return tabs


def _span_seconds(history: Iterable[AttemptRecord], day: str, end: int) -> int | None:
    """``T`` minus the first beat on ``T``'s own day, or ``None`` without one."""
    firsts = [
        beat.at
        for found in history
        if found.day == day
        for beat in found.beats
        if beat.at <= end
    ]
    return end - min(firsts) if firsts else None


def measure(
    credit: Credit,
    history: Sequence[AttemptRecord],
    *,
    cleared: AbstractSet[str] = frozenset(),
) -> Solve:
    """Measure one solve.

    Args:
        credit: The solve (its earliest credit).
        history: Every day-record of ``credit.slug``, in any order.
        cleared: Slugs already reviewed; a cleared slug is never flagged.

    Returns:
        The measurement. ``measured`` is false, and the numbers are zero or
        ``None``, when the window holds no beat.
    """
    end, day = credit.accepted_at, day_of(credit.accepted_at)
    beats = [beat for found in history for beat in found.beats if beat.at <= end]
    subs = [sub for found in history for sub in found.submissions.values()]
    subs = [sub for sub in subs if sub.at <= end]
    cut = min((sub.at for sub in subs), default=end)
    theory = next(
        (found.theory_at_solve for found in history if found.day == day), None
    )
    active = active_seconds((beat.at for beat in beats), end)
    theory = theory or THEORY_UNKNOWN
    measured = bool(beats)
    return Solve(
        slug=credit.slug,
        accepted_at=end,
        measured=measured,
        active_seconds=active,
        span_seconds=_span_seconds(history, day, end),
        tab_seconds=_tab_seconds(beats, end),
        failed=dict(
            sorted(Counter(s.status for s in subs if s.status != ACCEPTED).items())
        ),
        first_submission_active_seconds=active_seconds(
            (beat.at for beat in beats if beat.at <= cut), cut
        ),
        theory=theory,
        flagged=(
            measured
            and active > FLAG_SECONDS
            and theory == THEORY_DONE
            and credit.slug not in cleared
        ),
    )
