"""The curriculum order: which theory block a problem is served in.

Acceptance-rate order shuffles topics, so a pattern met once does not come back
for weeks and a problem needing a trick arrives before the trick was ever
taught (2026-11-21: 7 of 19 coached problems stalled on a missing idea). The
curriculum is an ordered list of units -- a set of LeetCode topic tags plus the
tutor module that teaches them -- and the suggestion list is served unit by unit.

**A problem belongs to the LATEST unit among its tags**, so every idea it needs
was taught before it is offered: an ``array`` problem that also carries
``bit-manipulation`` waits for the bit block. A tag no unit claims is ignored
when another tag maps, and sorts after every unit when none does; advanced
tags such as ``rolling-hash`` are left unclaimed on purpose, because an Easy
tagged that way is solvable without it.

**Display-only**, exactly like ``progress_cache.json``. It orders rows and
nothing else: no module that decides, charges or credits may import this one
(``test_display_only_imports.py`` pins it). A missing or malformed file falls back
to the acceptance order rather than emptying the list -- the lock must always
offer something to solve.
"""

from __future__ import annotations

from dataclasses import dataclass
import enum
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Final

from leetcode_guard._read_json import MISSING, read_json

if TYPE_CHECKING:
    from collections.abc import Iterable

    from leetcode_guard._problem import Problem

_logger: Final = logging.getLogger(__name__)

SHIPPED_CURRICULUM_FILE: Final = Path(__file__).parent / "curriculum.json"
CURRICULUM_FILE = SHIPPED_CURRICULUM_FILE
"""Read at call time, never bound as a default argument, so the test suite can
point it away from the shipped list (``_paths_fixture``)."""


class _MalformedError(ValueError):
    """The curriculum document has a shape this module refuses."""


@dataclass(frozen=True)
class Unit:
    """One theory block: the tags it claims and the tutor module teaching them."""

    unit_id: str
    tags: frozenset[str]
    subject: str = ""
    """Tutor subject id; empty when no theory is mapped to the unit."""
    modules: tuple[str, ...] = ()
    """Tutor module ids; the unit's theory is done when all of them are."""
    untagged: bool = False
    """Claims problems with no topic tags (LeetCode's JavaScript and pandas sets)."""


@dataclass(frozen=True)
class Curriculum:
    """The units in teaching order, and the order that settles membership."""

    units: tuple[Unit, ...]
    claim_rank: tuple[int, ...] = ()
    """Per unit, its place in the file's ``claim_order``; empty = teaching order.

    Membership ("the latest claiming unit") is ranked by this, not by the
    teaching order, so reordering what is taught first never moves a problem
    to another unit (stage 4, 2026-11-22: the new order applied to membership
    left ``prefix-sums`` with no Easy problem and ``scans`` with 664)."""

    def _rank(self, index: int) -> int:
        """Where unit ``index`` stands when two units claim one problem."""
        return self.claim_rank[index] if self.claim_rank else index

    def unit_index(self, topics: Iterable[str]) -> int:
        """Position (teaching order) of the unit a problem with these tags is in.

        Returns:
            The index of the claiming unit latest in the claim order, or
            ``len(units)`` -- after every block -- when no unit claims a tag.
        """
        tags = frozenset(topics)
        last = len(self.units)
        if not tags:
            return next((i for i, u in enumerate(self.units) if u.untagged), last)
        claiming = [i for i, u in enumerate(self.units) if u.tags & tags]
        return max(claiming, key=self._rank, default=last)


class Theory(enum.Enum):
    """Whether the tutor has taught a unit's theory (``_theory`` decides)."""

    NONE = "none"
    """No tutor module is mapped to the unit: nothing to wait for."""
    DONE = "done"
    PENDING = "pending"
    UNKNOWN = "unknown"
    """The tutor's files could not be read. Shown as pending, never as done:
    "cannot check" must not read as "taught"."""


@dataclass(frozen=True)
class Blocks:
    """The curriculum plus each unit's theory state, as of one resolve."""

    curriculum: Curriculum
    theory: tuple[Theory, ...]
    """One state per unit, in unit order."""

    def theory_of(self, problem: Problem) -> Theory:
        """The theory state of the block ``problem`` is served in."""
        index = self.curriculum.unit_index(problem.topics)
        return self.theory[index] if index < len(self.theory) else Theory.NONE

    def waits(self, problem: Problem) -> bool:
        """Whether the row is marked and pushed down: theory not yet taught."""
        return self.theory_of(problem) in {Theory.PENDING, Theory.UNKNOWN}

    def unit_id(self, problem: Problem) -> str:
        """The block's id, or ``""`` for a problem no unit claims."""
        index = self.curriculum.unit_index(problem.topics)
        units = self.curriculum.units
        return units[index].unit_id if index < len(units) else ""

    def key(self, problem: Problem) -> tuple[int, ...]:
        """What ``rank_pool`` sorts by between difficulty and acceptance.

        Taught blocks first, in curriculum order; then the waiting ones, also
        in curriculum order. Nothing is ever dropped.
        """
        return (int(self.waits(problem)), self.curriculum.unit_index(problem.topics))


def _unit(row: object) -> Unit:
    """Parse one unit row, refusing anything not exactly the expected shape."""
    if not isinstance(row, dict):
        message = f"unit is not an object: {row!r}"
        raise _MalformedError(message)
    unit_id, tags, tutor = row.get("id"), row.get("tags"), row.get("tutor", {})
    if not isinstance(unit_id, str) or not unit_id:
        message = f"unit id must be a non-empty string: {unit_id!r}"
        raise _MalformedError(message)
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        message = f"unit {unit_id}: tags must be a list of strings"
        raise _MalformedError(message)
    if not isinstance(tutor, dict):
        message = f"unit {unit_id}: tutor must be an object"
        raise _MalformedError(message)
    subject, modules = tutor.get("subject", ""), tutor.get("modules", [])
    named = (
        isinstance(subject, str)
        and isinstance(modules, list)
        and all(isinstance(module, str) and module for module in modules)
        and bool(subject and modules)
    )
    if tutor and not named:
        message = f"unit {unit_id}: tutor needs a subject and a list of modules"
        raise _MalformedError(message)
    return Unit(
        unit_id=unit_id,
        tags=frozenset(tags),
        subject=subject,
        modules=tuple(modules),
        untagged=row.get("untagged") is True,
    )


def _units(document: object) -> tuple[Unit, ...]:
    """Parse every unit; an id or a tag claimed twice is refused."""
    rows = document.get("units") if isinstance(document, dict) else None
    if not isinstance(rows, list) or not rows:
        message = "no units"
        raise _MalformedError(message)
    units = tuple(_unit(row) for row in rows)
    ids = [unit.unit_id for unit in units]
    claimed = [tag for row in rows for tag in row["tags"]]
    if len(set(ids)) != len(ids) or len(set(claimed)) != len(claimed):
        message = "a unit id or a tag appears twice"
        raise _MalformedError(message)
    return units


def _claim_rank(document: object, units: tuple[Unit, ...]) -> tuple[int, ...]:
    """Each unit's place in ``claim_order``, which must list every id once."""
    order = document.get("claim_order") if isinstance(document, dict) else None
    if order is None:
        return ()
    ids = [unit.unit_id for unit in units]
    if not isinstance(order, list) or sorted(map(str, order)) != sorted(ids):
        message = "claim_order must list every unit id exactly once"
        raise _MalformedError(message)
    return tuple(order.index(unit_id) for unit_id in ids)


def parse_curriculum(document: object) -> Curriculum | None:
    """The curriculum in ``document``, or ``None`` (logged) when malformed."""
    try:
        units = _units(document)
        return Curriculum(units=units, claim_rank=_claim_rank(document, units))
    except _MalformedError as exc:
        _logger.warning("curriculum refused, keeping the acceptance order: %s", exc)
        return None


def load_curriculum(path: Path | None = None) -> Curriculum | None:
    """Read the curriculum file.

    Args:
        path: The file; ``None`` means :data:`CURRICULUM_FILE` as it is *now*.

    Returns:
        The curriculum, or ``None`` when the file is absent (no curriculum
        configured) or unreadable or malformed (both logged at WARNING).
    """
    target = CURRICULUM_FILE if path is None else path
    document = read_json(
        target, _logger, "curriculum %s unreadable, keeping the old order: %s", target
    )
    if document is MISSING:
        return None
    return parse_curriculum(document)
