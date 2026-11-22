"""Theory credits: 12 signed teaching minutes on the current unit pay 1 credit.

A theory credit is an ordinary signed ledger row: ``kind: credit``,
``amount: 1``, ``entry_id: theory:<day>:<n>``, ``detail.source:
"tutor-theory"``, ``detail.unit`` and ``detail.minutes`` (the day's minutes
on the unit when it was minted). ``source`` is not ``"leetcode"``, so it
prices at 1 (``_balance.credit_value``) and never backs a review.

Rules (stage-4 SPEC, 2026-11-22):

* Only in THEORY(u), only minutes on u's modules (C1 ``detail.subject`` and
  ``detail.module``), only TODAY's (local day of ``ended_at``). Minutes taught
  before u's theory was done still pay in SOLVE(u); minutes after never do.
* The k-th credit for u on a day is minted once those minutes reach 12*k.
  ``n`` in the id is the day's running count over every unit. Minted rows are
  never revoked; a deleted ledger re-mints at most today's.
* Inputs are signed: the tutor's ``ledger.json`` and ``module_state.json`` and
  this guard's ledger. "Cannot check" mints nothing, logs a warning and never
  raises into the lock or the harvester.

:func:`poll_theory` is the one entry point; the one-minute harvester and the
lock's own poll both call it right after harvesting solves.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard._daycost import day_key
from leetcode_guard._ledger import CREDIT, LedgerEntry, sign
from leetcode_guard._ledger_io import append, save_ledger
from leetcode_guard._phase_file import write_phase
from leetcode_guard._phase_inputs import gather_phase
from leetcode_guard._tutor_signed import signed_rows, teaching_minutes

if TYPE_CHECKING:
    from datetime import date, datetime
    from pathlib import Path

    from leetcode_guard._ledger_io import Ledger
    from leetcode_guard._phase import PhaseState

_logger: Final = logging.getLogger(__name__)

MINUTES_PER_CREDIT: Final = 12
SOURCE_THEORY: Final = "tutor-theory"
TUTOR_LEDGER: Final = "ledger.json"


@dataclass(frozen=True)
class TheoryPoll:
    """What one poll saw and minted."""

    state: PhaseState | None
    """The phase decided now; ``None`` = an input could not be read."""
    minutes: int = 0
    """Today's paying minutes on the current unit."""
    minted: tuple[LedgerEntry, ...] = ()


def theory_entry(
    stamp: tuple[date, datetime],
    *,
    n: int,
    unit: str,
    minutes: int,
    key_file: Path | None,
) -> LedgerEntry:
    """The signed ``theory:<day>:<n>`` credit; ``stamp`` is (day, now)."""
    day, now = stamp
    return sign(
        LedgerEntry(
            entry_id=f"theory:{day_key(day)}:{n}",
            kind=CREDIT,
            day=day_key(day),
            created_at=now.isoformat(),
            amount=1,
            detail={"source": SOURCE_THEORY, "unit": unit, "minutes": str(minutes)},
        ),
        key_file=key_file,
    )


def due_credits(
    ledger: Ledger,
    state: PhaseState,
    minutes: int,
    *,
    stamp: tuple[date, datetime],
    key_file: Path | None = None,
) -> list[LedgerEntry]:
    """The credits ``minutes`` earn for ``state.unit`` today and are not minted yet."""
    day = stamp[0]
    if state.phase == "none":
        return []
    prefix = f"theory:{day_key(day)}:"
    today = [e for e in ledger.entries.values() if e.entry_id.startswith(prefix)]
    have = sum(1 for e in today if e.detail.get("unit") == state.unit)
    fresh: list[LedgerEntry] = []
    n = len(today)
    for k in range(have + 1, minutes // MINUTES_PER_CREDIT + 1):
        n += 1
        while ledger.has(f"{prefix}{n}"):
            n += 1
        fresh.append(
            theory_entry(
                stamp,
                n=n,
                unit=state.unit,
                minutes=k * MINUTES_PER_CREDIT,
                key_file=key_file,
            )
        )
    return fresh


def paying_minutes(
    state: PhaseState, *, day: date, key_file: Path | None = None
) -> int | None:
    """Today's signed minutes that pay for ``state``; ``None`` = cannot check."""
    if state.phase == "none" or not state.modules:
        return 0
    rows = signed_rows(TUTOR_LEDGER, key_file=key_file)
    if rows is None:
        return None
    return teaching_minutes(
        rows, state.subject, state.modules, day=day, until=state.done_at
    )


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
    write_phase(state, day=day, now=now, key_file=key_file)
    minutes = paying_minutes(state, day=day, key_file=key_file)
    if minutes is None:
        return TheoryPoll(state=state)
    fresh = due_credits(ledger, state, minutes, stamp=stamp, key_file=key_file)
    if fresh:
        append(ledger, fresh)
        save_ledger(ledger_path, ledger)
        _logger.info("theory: %d credit(s) for %s", len(fresh), state.unit)
    return TheoryPoll(state=state, minutes=minutes, minted=tuple(fresh))


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
