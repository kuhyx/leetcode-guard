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

from leetcode_guard._browser import find_tutor
from leetcode_guard._phase_view import PhaseView
from leetcode_guard._review_due import CLEAR, UNKNOWN, DueRead, DueStatus, ReviewWatch
from leetcode_guard._review_file_watch import DueFileWatch
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
        rework_target=None if theory else (_DEMO_SUBJECT, unit),
        review_targets=() if theory else ((_DEMO_SUBJECT, unit),),
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
    """Owns :attr:`view` and :attr:`review`.

    ``view`` is the last screen read, ``None`` until one is; ``review`` the
    tutor cards due in it, ``None`` off SOLVE.
    """

    def __init__(self, deps: GuardDeps, *, demo: bool) -> None:
        """Nothing read yet: the lock calls :meth:`refresh` before the window."""
        self._deps = deps
        self._demo = demo
        self._watch = ReviewWatch(key_file=deps.key_file)
        self._no_tutor_warned = False
        self._fell_open = False
        self.file_watch = DueFileWatch(self._file_matters)
        """One step per poller watch tick: ``True`` brings the poll forward."""
        self.view: PhaseView | None = None
        self.review: DueRead | None = None

    def refresh(self) -> bool:
        """Read the phase and the due cards once; keep the last phase if it fails.

        The due cards are asked on every call (T is now), so the review row
        comes and goes with the tutor's file and the clock: that is the whole
        repaint, on the poll that already runs.

        Returns:
            Whether the rows changed (a new unit, or review left), so the rows
            it brings can be verified.
        """
        read = self._read()
        changed = False
        if read is not None:
            changed = self.view is None or read.unit != self.view.unit
            self.view = read
        was_review = self._reviewing()
        self.review = self._read_review()
        return changed or (was_review and not self._reviewing())

    def _reviewing(self) -> bool:
        return self.review is not None and self.review.status is DueStatus.DUE

    def _file_matters(self) -> bool:
        """Whether a rewritten due file could change the screen: real SOLVE unit."""
        view = self.view
        return not (
            self._demo
            or self._fell_open
            or view is None
            or view.phase != "solve"
            or not view.review_targets
        )

    def fall_open(self) -> None:
        """The review Open failed to launch: SOLVE rows for the rest of the run.

        A review row whose Open cannot open is a gate nobody can satisfy (the
        2026-08-05 rule). Sticky on purpose: a flapping launcher must not take
        the rows away again. The next :meth:`refresh` brings them back.
        """
        if not self._fell_open:
            self._fell_open = True
            _logger.warning("the review could not be opened: showing the solve rows")

    def _read_review(self) -> DueRead | None:
        """Cards due in the SOLVE unit now; ``None`` off SOLVE or with no module.

        Never into the lock: any raise is "cannot check" (SOLVE rows, one
        warning per run), like the phase read. The demo never reads the live
        file: its fixture says nothing is due. A due answer needs a tutor to
        open, and a launch that failed once ended the rule for this run.
        """
        view = self.view
        if view is None or view.phase != "solve" or not view.review_targets:
            return None
        if self._demo:
            return CLEAR
        if self._fell_open:
            return UNKNOWN
        try:
            return self._due_now(view.review_targets)
        except Exception:  # pylint: disable=broad-exception-caught
            if self._watch.first_warning():
                _logger.exception("review due read raised; showing the solve rows")
            return UNKNOWN

    def _due_now(self, targets: tuple[tuple[str, str], ...]) -> DueRead:
        """The tutor's file read at the lock's clock; no launcher: not due."""
        at_ms = int(self._deps.moment().timestamp() * 1000)
        answer = self._watch.read(targets, at_ms)
        if answer.status is DueStatus.DUE and find_tutor() is None:
            if not self._no_tutor_warned:
                self._no_tutor_warned = True
                _logger.warning("cards are due but there is no tutor to open")
            return UNKNOWN
        return answer

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
