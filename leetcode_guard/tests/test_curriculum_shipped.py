"""The shipped curriculum's tutor mappings: ``sql`` and the 13 new-subject units.

Hermetic: the tutor directory is a scratch one, never the live tutor's.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from leetcode_guard import _curriculum
from leetcode_guard._curriculum import Theory, load_curriculum
from leetcode_guard._theory import unit_theory
from leetcode_guard.tests.test_theory import taught

if TYPE_CHECKING:
    from pathlib import Path

SUBJECT = "mysql-8-for-timed-sql-coding-tests-joins-and"
CARDS = {
    "s1": {"module": "sql-lessons", "suspended": False},
    "s2": {"module": "sql-lessons", "suspended": False},
    "g1": {"module": "select-group-basics", "suspended": False},
    "c1": {
        "module": "clause-order-where-vs-having-and-left-join",
        "suspended": False,
    },
    "d1": {"module": "date-format-codes-decimal-division-and", "suspended": False},
}


def tutor(tmp_path: Path, *cards: str) -> Path:
    """A scratch tutor dir for ``SUBJECT`` with the given cards taught."""
    root = tmp_path / "tutor"
    (root / "subjects" / SUBJECT).mkdir(parents=True)
    (root / "subjects" / SUBJECT / "cards.json").write_text(
        json.dumps(CARDS), encoding="utf-8"
    )
    lines = "".join(json.dumps(taught(SUBJECT, card)) + "\n" for card in cards)
    (root / "log.jsonl").write_text(lines, encoding="utf-8")
    return root


def shipped() -> _curriculum.Curriculum:
    """The curriculum file that ships, not the test suite's absent one."""
    curriculum = load_curriculum(_curriculum.SHIPPED_CURRICULUM_FILE)
    assert curriculum is not None
    return curriculum


ALGO_SUBJECT = "leetcode-easy-algorithms-in-typescript"
PANDAS_SUBJECT = "javascript-and-pandas-for-leetcode-easy"
ALGO_UNITS = [
    "scans",
    "hashing",
    "math",
    "bits",
    "sorting-greedy",
    "pointers-window",
    "prefix-sums",
    "stack-queue",
    "binary-search",
    "lists-recursion",
    "trees",
    "heap-dp",
]


def test_every_unit_maps_a_tutor_subject():
    """Each algorithm unit maps its own same-named module; js-pandas maps four."""
    mapped = {unit.unit_id: unit for unit in shipped().units if unit.subject}

    assert sorted(mapped) == sorted([*ALGO_UNITS, "sql", "js-pandas"])
    for unit_id in ALGO_UNITS:
        assert mapped[unit_id].subject == ALGO_SUBJECT
        assert mapped[unit_id].modules == (unit_id,)
    assert mapped["js-pandas"].subject == PANDAS_SUBJECT
    assert mapped["js-pandas"].modules == (
        "js-closures-timers",
        "js-promises-arrays",
        "pandas-select-filter-group",
        "pandas-clean-reshape",
    )
    assert mapped["sql"].subject == SUBJECT
    assert mapped["sql"].modules == (
        "sql-lessons",
        "select-group-basics",
        "clause-order-where-vs-having-and-left-join",
        "date-format-codes-decimal-division-and",
    )


def test_the_sql_unit_is_pending_until_every_module_is_taught(tmp_path: Path):
    """Lessons done, or all but the last module taught: still pending."""
    curriculum = shipped()
    index = [unit.unit_id for unit in curriculum.units].index("sql")

    half = unit_theory(curriculum, tutor(tmp_path / "half", "s1", "s2"))
    almost = unit_theory(curriculum, tutor(tmp_path / "almost", "s1", "s2", "g1", "c1"))
    full = unit_theory(
        curriculum, tutor(tmp_path / "full", "s1", "s2", "g1", "c1", "d1")
    )

    assert half[index] is Theory.PENDING
    assert almost[index] is Theory.PENDING
    assert full[index] is Theory.DONE
    # The scratch tutor has no cards for the other subjects: unknown, never done.
    assert {state for i, state in enumerate(full) if i != index} == {Theory.UNKNOWN}


TEACHING_ORDER = [
    "prefix-sums",
    "stack-queue",
    "lists-recursion",
    "binary-search",
    "bits",
    "heap-dp",
    "trees",
    "js-pandas",
    "pointers-window",
    "sorting-greedy",
    "hashing",
    "sql",
    "math",
    "scans",
]
"""kuhy's list (stage 4 SPEC, 2026-11-22): smallest unit first by Easy problems."""


def test_the_units_are_taught_smallest_first():
    """The theory-first flow walks the units in kuhy's confirmed order."""
    assert [unit.unit_id for unit in shipped().units] == TEACHING_ORDER


def test_membership_keeps_the_claim_order_the_counts_were_measured_with():
    """A problem's unit does not move when the teaching order does.

    kuhy's order is the 2026-11-21 per-unit Easy counts (20 .. 194), measured
    with "latest unit among the tags" over the OLD unit order. Applying that
    rule to the new order puts every ``array`` problem in ``scans`` (664 Easy)
    and leaves ``prefix-sums`` with none, so membership reads the claim order.
    """
    curriculum = shipped()
    ids = [unit.unit_id for unit in curriculum.units]

    assert ids[curriculum.unit_index(("array", "prefix-sum"))] == "prefix-sums"
    assert ids[curriculum.unit_index(("array", "bit-manipulation"))] == "bits"
    assert ids[curriculum.unit_index(("hash-table", "sorting"))] == "sorting-greedy"
    assert ids[curriculum.unit_index(("array",))] == "scans"
    assert ids[curriculum.unit_index(())] == "js-pandas"
