"""The shipped curriculum's one tutor mapping: the ``sql`` unit.

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


def test_only_the_sql_unit_maps_a_tutor_subject():
    """Every other unit stays unmapped until its tutor module exists."""
    mapped = {unit.unit_id: unit for unit in shipped().units if unit.subject}

    assert list(mapped) == ["sql"]
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
    assert {state for i, state in enumerate(full) if i != index} == {Theory.NONE}
