"""The finish credit: a tutor module signed done TODAY pays +1, once per module ever.

Added to the minute credits of :mod:`leetcode_guard._theory_credit`, so a module
finished in 9 minutes pays 1 and one finished in 24 pays 3. A ledger row like
any theory credit (``kind: credit``, ``amount: 1``, ``detail.source:
"tutor-theory"``) with its own id, ``theory-done:<subject>:<module>``: no day in
it, so ``done`` flipping back (a card added or suspended) and true again
never pays twice, and no ``theory:<day>:`` prefix, so it is never counted as a
minute credit (``due_credits``, ``minutes_into_credit``).

Rules (kuhy, 2026-11-22):

* Done = the module's latest verified C2 row says so, read as strictly as the
  phase machine reads it: one unverified row is "cannot check", nothing mints.
* Only when that row's ``day`` is today. A module done earlier never pays, so a
  deleted ledger re-mints at most today's finish.
* Only modules of the unit current when the poll starts (the last signed C3
  phase) or when it ends (the phase just decided): the poll that flips THEORY
  into SOLVE, or moves on to the next unit, still pays the unit it leaves.
  The tutor backfills ``done`` rows for units nobody taught; those never pay.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from leetcode_guard._curriculum import load_curriculum
from leetcode_guard._daycost import day_key
from leetcode_guard._ledger import CREDIT, LedgerEntry, sign
from leetcode_guard._phase_inputs import MODULE_STATE
from leetcode_guard._tutor_signed import done_days, signed_rows

if TYPE_CHECKING:
    from datetime import date, datetime
    from pathlib import Path

    from leetcode_guard._ledger_io import Ledger
    from leetcode_guard._phase import PhaseState

SOURCE_THEORY: Final = "tutor-theory"
FINISH_PREFIX: Final = "theory-done:"


def finish_entry(
    stamp: tuple[date, datetime],
    *,
    unit: str,
    subject: str,
    module: str,
    key_file: Path | None,
) -> LedgerEntry:
    """The signed ``theory-done:<subject>:<module>`` credit; ``stamp`` is (day, now)."""
    detail = {"unit": unit, "subject": subject, "module": module, "finish": "1"}
    return theory_row(f"{FINISH_PREFIX}{subject}:{module}", stamp, detail, key_file)


def theory_row(
    entry_id: str,
    stamp: tuple[date, datetime],
    detail: dict[str, str],
    key_file: Path | None,
) -> LedgerEntry:
    """A signed one-credit ``tutor-theory`` row; ``stamp`` is (day, now)."""
    day, now = stamp
    return sign(
        LedgerEntry(
            entry_id=entry_id,
            kind=CREDIT,
            day=day_key(day),
            created_at=now.isoformat(),
            amount=1,
            detail={"source": SOURCE_THEORY, **detail},
        ),
        key_file=key_file,
    )


def _candidates(
    state: PhaseState, before: PhaseState | None
) -> list[tuple[str, str, str]]:
    """(unit, subject, module) of the unit now current and the one that was."""
    found = [(state.unit, state.subject, m) for m in state.modules]
    if before is None or before.unit in {"", state.unit}:
        return found
    curriculum = load_curriculum()
    if curriculum is None:
        return found
    return found + [
        (unit.unit_id, unit.subject, module)
        for unit in curriculum.units
        if unit.unit_id == before.unit
        for module in unit.modules
    ]


def due_finish(
    ledger: Ledger,
    state: PhaseState,
    before: PhaseState | None,
    *,
    stamp: tuple[date, datetime],
    key_file: Path | None = None,
) -> list[LedgerEntry]:
    """The finish credits not minted yet; ``before`` is the phase the poll started in.

    Empty, with a warning, when C2 cannot be read strictly.
    """
    wanted = _candidates(state, before)
    if not wanted:
        return []
    rows = signed_rows(MODULE_STATE, key_file=key_file, strict=True)
    if rows is None:
        return []
    today = day_key(stamp[0])
    done = done_days(rows)
    return [
        finish_entry(
            stamp, unit=unit, subject=subject, module=module, key_file=key_file
        )
        for unit, subject, module in wanted
        if done.get((subject, module)) == today
        and not ledger.has(f"{FINISH_PREFIX}{subject}:{module}")
    ]
