"""Which unit screen the lock shows: read once per poll, kept when unreadable.

The phase is the rules side's verdict (SPEC C3/C5). The lock only *reads* it,
through one injected callable (``GuardSeams.phase``), and hands the result to
the view model. Nothing here decides a phase, mints a credit or touches the
tutor's files.

Read once before the window (``LeetcodeGuard.__init__``), once per poll, stored:
``build_model`` also runs from the reveal drain and the release path, and a
read there would hit the files several times per tick for nothing.

"Cannot check" is not "no": a read that raises keeps the last screen it
read, with a warning. Only a lock that never read one paints "none" --
today's list, which is also what the lock looked like before this flow.

The demo deletes its ledger every run, so it has no phase to read. It renders
each screen from a fixture instead, picked by :data:`DEMO_PHASE_ENV` (set by
``scripts/screenshot_lock.sh``) and honoured **only** in demo mode.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Final

from leetcode_guard._phase_view import PhaseView
from leetcode_guard._view_problems import INITIAL_ROWS

if TYPE_CHECKING:
    from leetcode_guard._lock_deps import GuardDeps
    from leetcode_guard._pool_resolve import PoolResolution
    from leetcode_guard._viewmodel import ViewModel

_logger: Final = logging.getLogger(__name__)

DEMO_PHASE_ENV: Final = "LEETCODE_GUARD_DEMO_PHASE"
"""``theory``, ``plan`` (THEORY, lessons not ready), ``solve`` or ``none``."""

_DEMO_SUBJECT: Final = "leetcode-easy-algorithms-in-typescript"


def _first_unit(pool: PoolResolution) -> tuple[str, int]:
    """The unit of the pool's best-ranked problem, and how many it has."""
    blocks = pool.blocks
    if blocks is None:
        return "", 0
    units = [blocks.unit_id(problem) for problem in pool.problems]
    unit = next((u for u in units if u), "")
    return unit, units.count(unit) if unit else 0


def demo_phase(name: str, pool: PoolResolution) -> PhaseView | None:
    """A fixture screen for the demo, on the pool's first unit; ``None`` if unknown."""
    if name not in {"theory", "plan", "solve", "none"}:
        return None
    unit, count = _first_unit(pool)
    if name == "none":
        return PhaseView(
            unit="",
            phase="none",
            cards_taught=None,
            cards_total=None,
            lessons_ready=True,
            minutes_per_credit=12,
            theory_minutes_today=0,
            solved=0,
            total=0,
            learn_target=None,
        )
    theory = name != "solve"
    return PhaseView(
        unit=unit,
        phase="theory" if theory else "solve",
        cards_taught=3 if theory else 12,
        cards_total=12,
        lessons_ready=name != "plan",
        minutes_per_credit=12,
        theory_minutes_today=7,
        solved=0 if theory else 1,
        total=count if theory else count + 1,
        learn_target=(_DEMO_SUBJECT, unit) if theory else None,
    )


def unit_rows(model: ViewModel, *, changed: bool) -> int:
    """How many rows to check live after a unit change; 0 otherwise.

    Only the top of the *whole* pool was verified before the window opened;
    a unit's problems can rank below it, so without this an already-solved
    one could sit on screen with an Open button that earns nothing.
    """
    if not changed or not model.screen.unit_list:
        return 0
    return min(len(model.problems), INITIAL_ROWS)


class PhaseReader:
    """Owns :attr:`view`: the last screen read, ``None`` until one is."""

    def __init__(self, deps: GuardDeps, *, demo: bool) -> None:
        """Nothing read yet: the lock calls :meth:`refresh` before the window."""
        self._deps = deps
        self._demo = demo
        self.view: PhaseView | None = None

    def refresh(self) -> bool:
        """Read the phase once; keep the last one if this read fails.

        Returns:
            Whether the unit changed, so the rows it brings can be verified.
        """
        read = self._read()
        if read is None:
            return False
        changed = self.view is None or read.unit != self.view.unit
        self.view = read
        return changed

    def _read(self) -> PhaseView | None:
        if self._demo and (name := os.environ.get(DEMO_PHASE_ENV)):
            return demo_phase(name, self._deps.pool)
        source = self._deps.seams.phase
        if source is None:
            return None
        try:
            return source()
        except Exception:  # pylint: disable=broad-exception-caught
            # Never into the lock: a raise here is a poll that never repaints.
            _logger.exception("the theory phase could not be read; keeping the last")
            return None
