"""Theory credits: 12 signed tutor minutes (lesson plus review) pay 1 credit.

A theory credit is an ordinary signed ledger row: ``kind: credit``,
``amount: 1``, ``entry_id: theory:<day>:<n>``, ``detail.source:
"tutor-theory"``, ``detail.unit``, ``detail.minutes`` (the day's pool when it
was minted) and ``detail.reviews`` (how many review minutes the unit's credits
had spent). ``source`` is not ``"leetcode"``, so it prices at 1
(``_balance.credit_value``) and never backs a review.

Rules (stage-4 SPEC, 2026-11-22; the pool is ``_theory_pool``):

* Lesson minutes: only in THEORY(u), only on u's modules (C1 ``detail.subject``
  and ``detail.module``), only TODAY's (local day of ``ended_at``). Minutes
  taught before u's theory was done still pay in SOLVE(u); minutes after never
  do.
* Review minutes (``detail.activity == "review"``) on any mapped card count
  one for one in every phase, ``none`` included, and share the counter.
* The k-th credit for u on a day is minted once the pool reaches 12*k. ``n`` in
  the id is the day's running count over every unit. Minted rows are never
  revoked; a deleted ledger re-mints at most today's.
* A module signed done today also pays +1, once per module ever
  (``_theory_finish``; ``theory-done:<subject>:<module>``, no day in the id,
  so it is never a minute credit).
* Inputs are signed: the tutor's ``ledger.json`` and ``module_state.json`` and
  this guard's ledger. "Cannot check" mints nothing, logs a warning and never
  raises into the lock or the harvester.

:func:`poll_theory` is the one entry point. The lock's own poll calls it right
after harvesting solves; the one-minute harvester calls it before them (a
LeetCode outage must not hold theory back) and again after a credited solve,
so a solve that finishes the unit moves C3 on in the same run.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard._balance import is_trusted
from leetcode_guard._daycost import day_key
from leetcode_guard._ledger import CREDIT, LedgerEntry, sign
from leetcode_guard._ledger_io import append, save_ledger
from leetcode_guard._phase_file import read_phase, write_phase
from leetcode_guard._phase_inputs import gather_phase
from leetcode_guard._theory_finish import SOURCE_THEORY, due_finish
from leetcode_guard._theory_pool import (
    MINUTES_PER_CREDIT,
    Tier,
    label,
    minted_for,
    minted_today,
    paying_pool,
)
from leetcode_guard._unit_finish import record_finishes

if TYPE_CHECKING:
    from datetime import date, datetime
    from pathlib import Path

    from leetcode_guard._ledger_io import Ledger
    from leetcode_guard._phase import PhaseState
    from leetcode_guard._theory_pool import Pool

_logger: Final = logging.getLogger(__name__)

__all__ = ["MINUTES_PER_CREDIT", "SOURCE_THEORY"]


@dataclass(frozen=True)
class TheoryPoll:
    """What one poll saw and minted."""

    state: PhaseState | None
    """The phase decided now; ``None`` = an input could not be read."""
    minutes: int = 0
    """Today's pool: lesson minutes on the current unit plus free review minutes."""
    minted: tuple[LedgerEntry, ...] = ()


def theory_entry(
    stamp: tuple[date, datetime], tier: Tier, *, n: int, key_file: Path | None
) -> LedgerEntry:
    """The signed ``theory:<day>:<n>`` credit; ``stamp`` is (day, now)."""
    day, now = stamp
    detail = {"source": SOURCE_THEORY, "unit": tier.unit}
    detail |= {"minutes": str(tier.minutes), "reviews": str(tier.reviews)}
    return sign(
        LedgerEntry(
            entry_id=f"theory:{day_key(day)}:{n}",
            kind=CREDIT,
            day=day_key(day),
            created_at=now.isoformat(),
            amount=1,
            detail=detail,
        ),
        key_file=key_file,
    )


def due_credits(
    ledger: Ledger,
    state: PhaseState,
    pool: Pool,
    *,
    stamp: tuple[date, datetime],
    key_file: Path | None = None,
) -> list[LedgerEntry]:
    """The credits ``pool`` earns the unit today and are not minted yet.

    The k-th credit records the ``max(0, 12*k - pool.lessons)`` review minutes
    it spent (``detail.reviews``). The unit is ``state.unit``, or ``review``
    in ``none``.
    """
    day = stamp[0]
    unit = label(state)
    prefix = f"theory:{day_key(day)}:"
    today = minted_today(ledger, day)
    have = minted_for(today, unit)
    fresh: list[LedgerEntry] = []
    n = len(today)
    for k in range(have + 1, pool.total // MINUTES_PER_CREDIT + 1):
        n += 1
        while ledger.has(f"{prefix}{n}"):
            n += 1
        cut = k * MINUTES_PER_CREDIT
        fresh.append(
            theory_entry(
                stamp,
                Tier(unit, cut, max(0, cut - pool.lessons)),
                n=n,
                key_file=key_file,
            )
        )
    return fresh


def minutes_into_credit(
    ledger: Ledger, state: PhaseState, minutes: int, *, day: date
) -> int:
    """Minutes already counted towards the next credit, 0..``MINUTES_PER_CREDIT``.

    The read side of :func:`due_credits`, over the same rows: ``minutes`` less
    12 for each credit minted for ``state.unit`` today. A credit due but not
    minted yet (``minutes // 12`` above the minted count) reads a full 12, so
    12 means "mint pending" and nothing else. ``minutes`` is the pool
    (``paying_minutes``); in ``none`` the credits are labelled ``review``.
    """
    have = minted_for(minted_today(ledger, day), label(state))
    return min(MINUTES_PER_CREDIT, max(0, minutes - MINUTES_PER_CREDIT * have))


def theory_credits(ledger: Ledger, *, day: date) -> tuple[int, int]:
    """(today's count, all-time value) of the trusted theory credits."""
    trusted = [
        entry
        for entry in ledger.entries.values()
        if entry.kind == CREDIT
        and entry.detail.get("source") == SOURCE_THEORY
        and is_trusted(entry, integrity_ok=ledger.integrity_ok)
    ]
    # By the row's day, not the id: a finish credit (``theory-done:...``) has no
    # day in its id and still counts as one of today's theory credits.
    today = sum(1 for entry in trusted if entry.day == day_key(day))
    return today, sum(entry.amount for entry in trusted)


def _note_finishes(
    ledger: Ledger, state: PhaseState, now: datetime, key_file: Path | None
) -> None:
    """C6 for the tutor's post-mortem; its own fence, so it never costs a credit."""
    try:
        record_finishes(ledger, state, now=now, key_file=key_file)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        name = type(exc).__name__
        _logger.warning("unit finish not recorded: %s", name, exc_info=True)


def _poll(
    ledger: Ledger,
    ledger_path: Path,
    stamp: tuple[date, datetime],
    key_file: Path | None,
) -> TheoryPoll:
    """The poll proper; :func:`poll_theory` fences it."""
    day, now = stamp
    state = gather_phase(ledger, key_file=key_file)
    if state is None:
        return TheoryPoll(state=None)
    before = read_phase(key_file)  # the phase this poll starts in, before C3 moves
    write_phase(state, day=day, now=now, key_file=key_file)
    _note_finishes(ledger, state, now, key_file)
    pool = paying_pool(state, ledger, day=day, key_file=key_file)
    if pool is None:
        return TheoryPoll(state=state)
    fresh = due_credits(ledger, state, pool, stamp=stamp, key_file=key_file)
    fresh += due_finish(ledger, state, before, stamp=stamp, key_file=key_file)
    if fresh:
        append(ledger, fresh)
        save_ledger(ledger_path, ledger)
        _logger.info("theory: %d credit(s) for %s", len(fresh), state.unit)
    return TheoryPoll(state=state, minutes=pool.total, minted=tuple(fresh))


def poll_theory(
    ledger: Ledger,
    ledger_path: Path,
    *,
    day: date,
    now: datetime,
    key_file: Path | None = None,
) -> TheoryPoll:
    """Decide the phase, rewrite C3 on change, mint due theory credits and save.

    ``ledger`` is the caller's loaded ledger and gains the minted rows, which
    are saved to ``ledger_path``; the caller then decides the day as it does
    after a solve. Never raises (``Exception`` only): a theory bug must cost
    the theory credit, never the lock or the harvest.
    """
    try:
        return _poll(ledger, ledger_path, (day, now), key_file)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _logger.warning("theory poll failed: %s", type(exc).__name__, exc_info=True)
        return TheoryPoll(state=None)
