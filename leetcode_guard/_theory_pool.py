"""The day's shared 12-minute counter: lesson minutes plus signed review minutes.

kuhy (2026-11-22): a review minute on ANY LeetCode card counts like a lesson
minute, in every phase (THEORY, SOLVE and ``none``), whatever the current unit.
Lesson minutes keep their rule (the current unit's modules, the THEORY window).

For the current unit ``u`` the pool is ``L_u + R_free``:

* ``L_u``: today's lesson minutes by the old rule; 0 in ``none``.
* ``R``: every review minute today (``_tutor_minutes.review_minutes``).
* ``R_free``: ``R`` less the review minutes already spent by credits minted
  today under OTHER unit labels, so a unit change never re-pays a review.

Each minted row records how many review minutes its label's credits had spent
when it was minted: ``detail.reviews = max(0, 12*k - L_u)`` for the k-th credit
of the day (a ledger detail value, so a string). What another label spent is
the ``reviews`` of its highest-``minutes`` row today; a row without the key
(minted before this change) spent 0. Only trusted rows count as spent, so an
edited row (a credit nobody pays) cannot be turned into free review minutes
elsewhere: editing one costs the credit it was.

``none`` labels its rows :data:`REVIEW_LABEL`. Rows are never revoked.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard._balance import is_trusted
from leetcode_guard._curriculum import load_curriculum
from leetcode_guard._daycost import day_key
from leetcode_guard._phase_file import phase_since
from leetcode_guard._tutor_minutes import review_minutes, teaching_minutes
from leetcode_guard._tutor_signed import signed_rows

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

    from leetcode_guard._ledger import LedgerEntry
    from leetcode_guard._ledger_io import Ledger
    from leetcode_guard._phase import PhaseState

_logger: Final = logging.getLogger(__name__)

MINUTES_PER_CREDIT: Final = 12
TUTOR_LEDGER: Final = "ledger.json"
REVIEW_LABEL: Final = "review"
"""``detail.unit`` of a credit minted in ``none`` (no unit is current)."""


@dataclass(frozen=True)
class Tier:
    """What one minted credit records: its label, the pool minutes, reviews spent."""

    unit: str
    """``detail.unit``: the unit id, or :data:`REVIEW_LABEL` in ``none``."""
    minutes: int
    """``detail.minutes``: ``12*k`` for the k-th credit of the day."""
    reviews: int = 0
    """``detail.reviews``: the review minutes among them, ``max(0, minutes - L_u)``."""


@dataclass(frozen=True)
class Pool:
    """Today's paying minutes for the current unit."""

    lessons: int
    """``L_u``: lesson minutes by the unit's own rule."""
    free_reviews: int
    """``R_free``: review minutes no other unit's credit has spent."""

    @property
    def total(self) -> int:
        """The counter the credits are cut from."""
        return self.lessons + self.free_reviews


def label(state: PhaseState) -> str:
    """The ``detail.unit`` a credit minted for ``state`` carries."""
    return REVIEW_LABEL if state.phase == "none" else state.unit


def minted_today(ledger: Ledger, day: date) -> list[LedgerEntry]:
    """Every ``theory:<day>:<n>`` row in the ledger, trusted or not."""
    prefix = f"theory:{day_key(day)}:"
    return [e for e in ledger.entries.values() if e.entry_id.startswith(prefix)]


def minted_for(today: list[LedgerEntry], unit: str) -> int:
    """How many of today's theory rows carry the label ``unit``."""
    return sum(1 for e in today if e.detail.get("unit") == unit)


def _count(raw: str | None) -> int:
    """A ledger detail value as a count; anything but digits is 0."""
    return int(raw) if raw is not None and raw.isascii() and raw.isdigit() else 0


def spent_elsewhere(today: list[LedgerEntry], unit: str, *, integrity_ok: bool) -> int:
    """Review minutes spent by today's trusted credits under labels other than ``unit``.

    Per label, the ``reviews`` of its highest-``minutes`` row (ties: the
    larger), because a later credit has spent at least what an earlier one did.
    """
    best: dict[str, tuple[int, int]] = {}
    for entry in today:
        other = entry.detail.get("unit", "")
        if other == unit or not is_trusted(entry, integrity_ok=integrity_ok):
            continue
        seen = (
            _count(entry.detail.get("minutes")),
            _count(entry.detail.get("reviews")),
        )
        best[other] = max(best.get(other, (0, 0)), seen)
    return sum(spent for _, spent in best.values())


def _mapped() -> frozenset[tuple[str, str]] | None:
    """Every (subject, module) any curriculum unit maps; ``None`` = no curriculum."""
    curriculum = load_curriculum()
    if curriculum is None:
        return None
    return frozenset(
        (unit.subject, module) for unit in curriculum.units for module in unit.modules
    )


def _lessons(
    state: PhaseState, rows: list[dict[str, object]], day: date, key_file: Path | None
) -> int:
    """Today's lesson minutes for ``state``; 0 without modules or a matching C3."""
    if state.phase == "none" or not state.modules:
        return 0
    since = phase_since(state, key_file)
    if since is None:
        return 0
    return teaching_minutes(
        rows, state.subject, state.modules, day=day, window=(since, state.done_at)
    )


def paying_pool(
    state: PhaseState, ledger: Ledger, *, day: date, key_file: Path | None = None
) -> Pool | None:
    """Today's pool for ``state``; ``None`` = cannot check (logged), mint nothing.

    The tutor's ledger and the curriculum must both be readable. Lesson minutes
    also need C3 (else 0); review minutes need neither C3 nor ``since``.
    """
    rows = signed_rows(TUTOR_LEDGER, key_file=key_file)
    mapped = _mapped()
    if rows is None or mapped is None:
        return None
    reviews = review_minutes(rows, mapped, day=day)
    spent = spent_elsewhere(
        minted_today(ledger, day), label(state), integrity_ok=ledger.integrity_ok
    )
    return Pool(
        lessons=_lessons(state, rows, day, key_file),
        free_reviews=max(0, reviews - spent),
    )


def paying_minutes(
    state: PhaseState, ledger: Ledger, *, day: date, key_file: Path | None = None
) -> int | None:
    """The pool's total for ``state``; ``None`` = cannot check (display = mint)."""
    pool = paying_pool(state, ledger, day=day, key_file=key_file)
    return None if pool is None else pool.total
