"""The suggestion list's live filter. Continued from :mod:`test_viewmodel`.

Split off for the 250-line cap. These are the unit-level half of the fix for
a solved problem holding a slot; the user-level half is
``test_scenarios_part4.py``.
"""

from __future__ import annotations

from leetcode_guard._viewmodel import build_problem_lines
from leetcode_guard.tests.test_viewmodel import pool_of


def test_a_problem_solved_since_the_pool_was_resolved_is_dropped():
    """The reported bug: a solve mid-lock must free its slot.

    Backfill comes from the bench the pool was resolved with, so the list
    stays full and the numbering closes up rather than leaving a hole.
    """
    lines, dropped = build_problem_lines(
        pool_of("a", "b", "c"), limit=2, solved_slugs=frozenset({"a"})
    )

    assert [line.label.split(". ", 1)[1].split("  --")[0] for line in lines] == [
        "B",
        "C",
    ]
    assert [line.label.split(".")[0] for line in lines] == ["1", "2"]
    assert dropped == ("A",)


def test_only_solves_inside_the_display_window_are_reported():
    """A solve far down the bench costs no slot, so it is not announced.

    The acknowledgement exists to explain a row that vanished. Naming a
    problem the user never saw would be noise, and after a few days of debt
    it would be a lot of noise.
    """
    lines, dropped = build_problem_lines(
        pool_of("a", "b", "c"), limit=1, solved_slugs=frozenset({"c"})
    )

    assert len(lines) == 1
    assert dropped == ()


def test_a_wholly_solved_pool_yields_no_lines():
    lines, dropped = build_problem_lines(
        pool_of("a", "b"), limit=8, solved_slugs=frozenset({"a", "b"})
    )

    assert lines == ()
    assert dropped == ("A", "B")
