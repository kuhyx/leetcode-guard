"""Gather the phase machine's inputs from disk; ``None`` means "cannot check".

Kept apart from :mod:`leetcode_guard._phase` so the decision stays pure. Each
input that cannot be read answers ``None`` with a warning, and so does the
whole gather: a missing pool must never read as "every Easy problem solved",
and a missing C2 file must never read as "no theory done" on a machine that
had moved on. The caller then holds the last signed phase (``_phase_file``).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard import _constants
from leetcode_guard._balance import is_trusted
from leetcode_guard._curriculum import load_curriculum
from leetcode_guard._ledger import CREDIT, SEEN
from leetcode_guard._phase import PhaseState, decide_phase
from leetcode_guard._pool_cache import read_cache
from leetcode_guard._tutor_signed import module_done, signed_rows

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from leetcode_guard._curriculum import Curriculum
    from leetcode_guard._ledger_io import Ledger
    from leetcode_guard._problem import Problem

_logger: Final = logging.getLogger(__name__)

MODULE_STATE: Final = "module_state.json"
"""Contract C2, in the tutor's data dir."""


def easy_by_unit(
    curriculum: Curriculum, problems: Iterable[Problem]
) -> tuple[frozenset[str], ...]:
    """Per unit, the slugs of its free (not premium) Easy problems."""
    found: list[set[str]] = [set() for _ in curriculum.units]
    for problem in problems:
        if problem.difficulty != "Easy" or problem.paid_only:
            continue
        index = curriculum.unit_index(problem.topics)
        if index < len(found):
            found[index].add(problem.title_slug)
    return tuple(frozenset(slugs) for slugs in found)


def trusted_solved_slugs(ledger: Ledger) -> frozenset[str]:
    """Slugs with a trusted ``credit`` or ``seen`` row in the guard's ledger."""
    return frozenset(
        entry.detail["title_slug"]
        for entry in ledger.entries.values()
        if entry.kind in {CREDIT, SEEN}
        and entry.detail.get("title_slug")
        and is_trusted(entry, integrity_ok=ledger.integrity_ok)
    )


def gather_phase(ledger: Ledger, *, key_file: Path | None = None) -> PhaseState | None:
    """The phase now, or ``None`` (logged) when any input cannot be read."""
    curriculum = load_curriculum()
    if curriculum is None:
        _logger.warning("no curriculum: the theory phase cannot be decided")
        return None
    pool = read_cache(_constants.POOL_CACHE_FILE)
    if pool is None:
        _logger.warning("no problem pool: the theory phase cannot be decided")
        return None
    rows = signed_rows(MODULE_STATE, key_file=key_file)
    if rows is None:
        return None
    return decide_phase(
        curriculum,
        easy_by_unit(curriculum, pool.problems),
        trusted_solved_slugs(ledger),
        module_done(rows),
    )
