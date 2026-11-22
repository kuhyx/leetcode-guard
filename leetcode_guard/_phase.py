"""The theory-first state machine: which unit is current, and in which phase.

Pure: :func:`decide_phase` takes its inputs as values and does no I/O
(``_phase_inputs`` gathers them). Units are walked in teaching order
(``curriculum.json``); the current unit is the first one not finished, and a
unit is finished when its theory is done AND every free Easy problem of it is
solved.

* THEORY(u): u's theory is not done. Teaching minutes on u's modules pay, and
  ``teachable`` lists them for the tutor (contract C3).
* SOLVE(u): theory done, Easy problems remain. Nothing is teachable.
* none: every unit is finished.

Which inputs are trusted, and why:

* **Theory done** comes ONLY from verified C2 rows (the tutor's signed
  ``module_state.json``): a unit's theory is done when every mapped module's
  latest signed row says ``done``. No row means not done. The tutor's unsigned
  ``log.jsonl``/``cards.json`` never reach this module (``_theory`` reads them
  for display; ``test_display_only_imports.py`` bans it here).
* **Solved** comes from the guard's own ledger: trusted ``credit`` and ``seen``
  rows (``_balance.is_trusted``), keyed by ``title_slug``.
* **A unit's Easy set** is the problem pool (``pool_cache.json``, unsigned)
  split by the curriculum's claim rule. Premium problems are left out: they
  cannot be opened, so a unit holding one could never finish. Editing the
  pool can move the phase, but it can never mint: a theory credit still needs
  signed tutor minutes, and a solve still needs LeetCode's accepted feed.
* **The order and the mapping** (``curriculum.json``) ship with the package.

A unit with no tutor mapping has nothing to teach: its theory counts as done.
Rework (a module flipping back to not done) puts the unit back in THEORY with
no extra code: the latest C2 row wins.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from leetcode_guard._curriculum import Curriculum, Unit
    from leetcode_guard._phase_view import Phase


@dataclass(frozen=True)
class PhaseState:
    """Where the machine stands, as decided from signed inputs."""

    unit: str
    """The current unit's id; ``""`` when every unit is finished."""
    phase: Phase
    subject: str = ""
    modules: tuple[str, ...] = ()
    """The current unit's tutor mapping (empty in ``none``)."""
    solved: int = 0
    total: int = 0
    """Free Easy problems of the current unit: solved, and all of them."""
    done_at: float | None = None
    """In SOLVE, when the unit's theory became done (its modules' latest signed
    ``at``): teaching minutes up to then still pay, later ones never do."""

    @property
    def teachable(self) -> tuple[tuple[str, str], ...]:
        """The (subject, module) pairs the tutor may teach now: u's, in THEORY only."""
        if self.phase != "theory":
            return ()
        return tuple((self.subject, module) for module in self.modules)


NONE_STATE = PhaseState(unit="", phase="none")


def theory_done(unit: Unit, done: Mapping[tuple[str, str], bool]) -> bool:
    """Whether every module mapped to ``unit`` has a latest signed ``done``."""
    return all(done.get((unit.subject, module), False) for module in unit.modules)


def decide_phase(
    curriculum: Curriculum,
    easy_by_unit: Sequence[frozenset[str]],
    solved: frozenset[str],
    done: Mapping[tuple[str, str], bool],
) -> PhaseState:
    """The current unit and phase.

    Args:
        curriculum: The units in teaching order.
        easy_by_unit: Per unit (same order), the slugs of its free Easy problems.
        solved: Slugs the guard's ledger holds a trusted solve for.
        done: The latest verified C2 ``done`` per (subject, module).

    Returns:
        The first unfinished unit in THEORY or SOLVE, else :data:`NONE_STATE`.
    """
    for unit, easy in zip(curriculum.units, easy_by_unit, strict=True):
        taught = theory_done(unit, done)
        if taught and easy <= solved:
            continue
        return PhaseState(
            unit=unit.unit_id,
            phase="solve" if taught else "theory",
            subject=unit.subject,
            modules=unit.modules,
            solved=len(easy & solved),
            total=len(easy),
        )
    return NONE_STATE
