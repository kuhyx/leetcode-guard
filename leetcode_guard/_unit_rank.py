"""The suggestion order in THEORY and SOLVE: the current unit's Easy problems first.

kuhy, 2026-11-22: "I opened leetcode lock and I got a wall of leetcode
problems". While a unit is current, its unsolved Easy problems are the five
rows; in "none" the order is exactly the pre-stage-4 one (``Blocks.key``).

The phase comes from the same machine the lock's header reads
(``_phase_inputs.phase_of`` over signed C2 and the pool being ranked), and
when C2 cannot be read, from the last signed phase (C3), the same fallback the
header takes, so the rows never contradict the header. Membership is the
machine's own rule: ``Curriculum.unit_index`` and ``difficulty == "Easy"``
(``rank_pool`` already drops premium problems).

Only the sort key changes: ranking still happens first, then only the top N
are verified live (``_pool_verify``), never the whole pool.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._phase_file import read_phase
from leetcode_guard._phase_inputs import phase_of

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

    from leetcode_guard._curriculum import Blocks, Curriculum
    from leetcode_guard._problem import Problem


def _focus_index(
    curriculum: Curriculum,
    problems: Iterable[Problem],
    solved: frozenset[str],
    key_file: Path | None,
) -> int | None:
    """The current unit's position, or ``None`` in "none" or when unknown."""
    state = phase_of(curriculum, problems, solved, key_file=key_file)
    if state is None:
        state = read_phase(key_file)
    if state is None or state.phase == "none":
        return None
    ids = [unit.unit_id for unit in curriculum.units]
    return ids.index(state.unit) if state.unit in ids else None


def focus_key(
    blocks: Blocks,
    problems: Iterable[Problem],
    solved: frozenset[str],
    *,
    key_file: Path | None = None,
) -> Callable[[Problem], tuple[int, ...]]:
    """The block key for ``rank_pool``, led by "is an Easy of the current unit".

    ``rank_pool`` sorts difficulty first, so the lead element only reorders
    the Easy problems; it goes before ``Blocks.key`` because the current unit
    in THEORY is untaught by definition, which ``Blocks.key`` sorts last.
    """
    index = _focus_index(blocks.curriculum, problems, solved, key_file)
    if index is None:
        return blocks.key
    unit_index = blocks.curriculum.unit_index

    def key(problem: Problem) -> tuple[int, ...]:
        here = problem.difficulty == "Easy" and unit_index(problem.topics) == index
        return (int(not here), *blocks.key(problem))

    return key
