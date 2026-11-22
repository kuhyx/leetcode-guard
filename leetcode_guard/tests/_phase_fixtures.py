"""A two-unit curriculum, a pool spread over it, and one ``PhaseView`` per screen.

Shared by the ``test_*phase*`` modules. The pool interleaves the units on
purpose: a view that forgot to filter would show ``stack-*`` rows on the
``prefix-sums`` card, and the slug lists in the assertions would say so.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from leetcode_guard._curriculum import Blocks, Theory, parse_curriculum
from leetcode_guard._phase_view import PhaseView
from leetcode_guard._pool_resolve import PoolResolution
from leetcode_guard.tests.test_problem import make

SUBJECT = "leetcode-easy-algorithms-in-typescript"

_DOCUMENT = {
    "version": 1,
    "units": [
        {
            "id": "prefix-sums",
            "tags": ["prefix-sum"],
            "tutor": {"subject": SUBJECT, "modules": ["prefix-sums"]},
        },
        {
            "id": "stack-queue",
            "tags": ["stack"],
            "tutor": {"subject": SUBJECT, "modules": ["stack-queue"]},
        },
    ],
}

PREFIX = ("range-sum", "pivot-index", "running-sum")
STACK = ("valid-parens", "min-stack")
OTHER = ("lonely-problem",)
"""A problem no unit claims: it sorts after every unit."""


def _blocks() -> Blocks:
    curriculum = parse_curriculum(_DOCUMENT)
    assert curriculum is not None
    return Blocks(curriculum=curriculum, theory=(Theory.PENDING, Theory.PENDING))


def unit_pool(*, blocks: bool = True) -> PoolResolution:
    """Every fixture problem, the units interleaved, ranked best first."""
    problems = (
        make("valid-parens", topics=["stack"]),
        make("range-sum", topics=["prefix-sum"]),
        make("lonely-problem", topics=["array"]),
        make("pivot-index", topics=["prefix-sum"]),
        make("min-stack", topics=["stack"]),
        make("running-sum", topics=["prefix-sum"]),
    )
    return PoolResolution(
        problems=problems,
        source="cache",
        notes=(),
        blocks=_blocks() if blocks else None,
    )


THEORY = PhaseView(
    unit="prefix-sums",
    phase="theory",
    cards_taught=3,
    cards_total=12,
    lessons_ready=True,
    minutes_per_credit=12,
    theory_minutes_today=7,
    solved=0,
    total=3,
    learn_target=(SUBJECT, "prefix-sums"),
)
SOLVE = replace(
    THEORY, phase="solve", cards_taught=12, solved=1, total=3, learn_target=None
)
NONE = replace(
    THEORY,
    unit="",
    phase="none",
    cards_taught=None,
    cards_total=None,
    solved=0,
    total=0,
    learn_target=None,
)
NEXT = replace(
    THEORY,
    unit="stack-queue",
    cards_taught=0,
    cards_total=8,
    total=2,
    learn_target=(SUBJECT, "stack-queue"),
)
"""THEORY of the next unit, the screen SOLVE(prefix-sums) hands over to."""


def phase(**changes: Any) -> PhaseView:
    """``THEORY`` with ``changes`` applied."""
    return replace(THEORY, **changes)
