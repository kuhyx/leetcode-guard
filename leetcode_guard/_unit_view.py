"""The lock's view of the current unit (SPEC C5), rebuilt on every repaint.

:func:`unit_view` makes the ``Callable[[], PhaseView]`` the lock window calls
(``GuardSeams.phase``). Read-only: it never polls, mints or writes C3; that is
``_theory_credit.poll_theory``'s job.

Where each field comes from:

* ``unit``, ``phase``, ``solved``, ``total``: ``gather_phase`` over the guard
  ledger, signed C2 and the pool, the decision the minting itself makes.
* ``theory_minutes_today``: ``_theory_credit.paying_minutes``, the number the
  minting counts; "cannot check" (logged there) shows 0.
* ``minutes_per_credit``: ``_theory_credit.MINUTES_PER_CREDIT``.
* ``learn_target``: THEORY only, the unit's first module (curriculum order)
  whose latest signed C2 row is not done.
* ``rework_target``: SOLVE only, the unit's first module (phase 2's ``?``).
* ``cards_taught``, ``cards_total``, ``lessons_ready``: the tutor's UNSIGNED
  ``cards.json``/``log.jsonl`` (``_theory.module_cards``) over the unit's
  modules; ``None`` when unreadable. ``lessons_ready``: the learn target's
  module has a live card.

**Display-only**, because of those unsigned files: nothing that decides,
charges or credits may import this module (``test_display_only_imports.py``).

Never raises into the lock. "Cannot check" (``gather_phase`` answers
``None``) and any bug (logged at warning) both show the last signed phase
(C3) with no counts and no cards; if even that read fails, "none", which is
the list as it was before stage 4. The lock shows those as 0; the read-only
surfaces (``--status``, MCP, the snapshot) take :func:`read_unit`, which also
says where the view came from, so they can show unknown instead.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Final, Literal

from leetcode_guard._daycost import local_today
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard._phase import NONE_STATE
from leetcode_guard._phase_file import read_phase
from leetcode_guard._phase_inputs import MODULE_STATE, gather_phase
from leetcode_guard._phase_view import PhaseView
from leetcode_guard._theory import module_cards
from leetcode_guard._theory_credit import MINUTES_PER_CREDIT, paying_minutes
from leetcode_guard._tutor_signed import module_done, signed_rows

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from datetime import date
    from pathlib import Path

    from leetcode_guard._phase import PhaseState

_logger: Final = logging.getLogger(__name__)

Cards = dict[str, tuple[int, int]]
Source = Literal["live", "held", "unknown"]


@dataclass(frozen=True)
class UnitRead:
    """One read of the unit: the lock's view plus what that view cannot say."""

    view: PhaseView
    source: Source
    """``live``: decided now from the signed inputs. ``held``: the last signed
    phase (C3), its counts unknown. ``unknown``: not even C3 was readable."""
    minutes: int | None
    """Today's paying minutes; ``None`` = cannot check (the view shows 0)."""


def unit_view(
    ledger_path: Path,
    *,
    key_file: Path | None = None,
    today: Callable[[], date] = local_today,
) -> Callable[[], PhaseView]:
    """The repaint callable: each call reads the files and the day afresh.

    Args:
        ledger_path: The guard ledger (``LEDGER_FILE`` in production).
        key_file: The HMAC key; ``None`` = the shared key.
        today: The day whose minutes count, asked on every call, so a lock
            left open past midnight counts the new day.
    """

    def view() -> PhaseView:
        return view_now(ledger_path, day=today(), key_file=key_file)

    return view


def view_now(
    ledger_path: Path, *, day: date, key_file: Path | None = None
) -> PhaseView:
    """The view now. Never raises (``Exception`` only)."""
    return read_unit(ledger_path, day=day, key_file=key_file).view


def read_unit(
    ledger_path: Path, *, day: date, key_file: Path | None = None
) -> UnitRead:
    """The view now and its source. Never raises (``Exception`` only)."""
    try:
        return _live(ledger_path, day, key_file)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _logger.warning(
            "unit view failed, holding the last signed phase: %s",
            type(exc).__name__,
            exc_info=True,
        )
    return _held(key_file)


def _live(ledger_path: Path, day: date, key_file: Path | None) -> UnitRead:
    """Decide from the signed inputs, then add the display-only counts."""
    ledger = load_ledger(ledger_path, key_file=key_file)
    state = gather_phase(ledger, key_file=key_file)
    if state is None:
        return _held(key_file)
    minutes = paying_minutes(state, day=day, key_file=key_file)
    rows = signed_rows(MODULE_STATE, key_file=key_file, strict=True)
    done = {} if rows is None else module_done(rows)
    cards = module_cards(state.subject, state.modules) if state.modules else None
    view = _assemble(state, minutes=minutes or 0, done=done, cards=cards)
    return UnitRead(view=view, source="live", minutes=minutes)


def _held(key_file: Path | None) -> UnitRead:
    """The last signed phase (C3) with no counts or cards; "none" if unreadable."""
    try:
        state = read_phase(key_file)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _logger.warning(
            "last signed phase unreadable, showing none: %s",
            type(exc).__name__,
            exc_info=True,
        )
        state = None
    view = _assemble(
        NONE_STATE if state is None else state, minutes=0, done={}, cards=None
    )
    return UnitRead(
        view=view, source="unknown" if state is None else "held", minutes=None
    )


def _learn_target(
    state: PhaseState, done: Mapping[tuple[str, str], bool]
) -> tuple[str, str] | None:
    """THEORY: the first module not done (the first one if all read done)."""
    if state.phase != "theory" or not state.modules:
        return None
    pending = (m for m in state.modules if not done.get((state.subject, m), False))
    return (state.subject, next(pending, state.modules[0]))


def _assemble(
    state: PhaseState,
    *,
    minutes: int,
    done: Mapping[tuple[str, str], bool],
    cards: Cards | None,
) -> PhaseView:
    """The C5 record for ``state``."""
    target = _learn_target(state, done)
    taught = total = None
    ready = False
    if cards is not None:
        taught = sum(n for n, _ in cards.values())
        total = sum(n for _, n in cards.values())
        ready = target is not None and cards.get(target[1], (0, 0))[1] > 0
    return PhaseView(
        unit=state.unit,
        phase=state.phase,
        cards_taught=taught,
        cards_total=total,
        lessons_ready=ready,
        minutes_per_credit=MINUTES_PER_CREDIT,
        theory_minutes_today=minutes,
        solved=state.solved,
        total=state.total,
        learn_target=target,
        rework_target=(
            (state.subject, state.modules[0])
            if state.phase == "solve" and state.modules
            else None
        ),
    )
