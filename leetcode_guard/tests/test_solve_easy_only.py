"""SOLVE(u) shows u's unsolved free Easy problems and nothing else (kuhy, 2026-11-22).

No backfill from other units, no Medium or Hard; fewer rows when fewer remain.
THEORY, "none" and an unknown phase keep today's lists. A filter that would
leave the surface empty falls back to today's narrowing with a warning: the
lock must always offer a way to do the thing it demands (2026-08-05).
"""

from __future__ import annotations

import logging

import pytest

from leetcode_guard import _viewmodel_lines
from leetcode_guard._gate import decide
from leetcode_guard._ledger_io import Ledger
from leetcode_guard._pool_resolve import PoolResolution
from leetcode_guard._viewmodel import build_problem_lines, build_viewmodel
from leetcode_guard._viewmodel_phase import PHASE_ROWS, build_phase_screen
from leetcode_guard._viewmodel_source import ViewSource
from leetcode_guard.tests._ledger_fixtures import MONDAY, NOW
from leetcode_guard.tests._phase_fixtures import NONE, SOLVE, THEORY, unit_pool
from leetcode_guard.tests.test_problem import make
from leetcode_guard.tests.test_viewmodel import CHECKED_AT, OK_PROBE, SIGNED_OUT

EASY = tuple(f"pre-easy-{n:02d}" for n in range(13))
"""prefix-sums' unsolved free Easy problems, in the order the ranking gave."""
MEDIUM = ("pre-medium-a", "pre-medium-b")
HARD = ("pre-hard",)
STACK_EASY = ("stack-easy-a", "stack-easy-b")
LONELY = "lonely-easy"
PREMIUM = "pre-premium"


@pytest.fixture(autouse=True)
def _fresh_warning_latch() -> None:
    """One warning per unit and process: each test starts with none sent."""
    _viewmodel_lines.WARNED.clear()


def pool() -> PoolResolution:
    """The ranked pool: prefix-sums' Easy lead, then everything else."""
    problems = (
        *(make(slug, topics=["prefix-sum"]) for slug in EASY),
        make(PREMIUM, topics=["prefix-sum"], paid_only=True),
        *(make(slug, topics=["stack"]) for slug in STACK_EASY),
        make(LONELY, topics=["array"]),
        *(make(slug, topics=["prefix-sum"], difficulty="Medium") for slug in MEDIUM),
        *(make(slug, topics=["stack"], difficulty="Medium") for slug in ("stk-med",)),
        *(make(slug, topics=["prefix-sum"], difficulty="Hard") for slug in HARD),
    )
    return PoolResolution(
        problems=problems, source="cache", notes=(), blocks=unit_pool().blocks
    )


def slugs(
    phase, *, solved: frozenset[str] = frozenset(), limit: int = 99, the_pool=None
):
    """The slugs on the lock's rows for ``phase``."""
    model = build_viewmodel(
        decide(Ledger(), day=MONDAY, now=NOW),
        ViewSource(
            the_pool or pool(),
            SIGNED_OUT,
            limit=limit,
            solved_slugs=solved,
            phase=phase,
        ),
        OK_PROBE,
        checked_at=CHECKED_AT,
    )
    return [line.slug for line in model.problems]


def test_a_unit_with_thirteen_easy_left_shows_exactly_those_in_ranked_order():
    """Not the unit's Medium and Hard, not another unit's Easy, not the premium one."""
    assert slugs(SOLVE) == list(EASY)


def test_three_left_means_three_rows_and_no_backfill():
    """The set ran short: the tail rows are simply not there."""
    done = frozenset(EASY[3:])

    assert slugs(SOLVE, solved=done) == list(EASY[:3])


def test_a_solve_mid_lock_refills_only_from_the_unit():
    """A freed slot is taken by the next Easy of the unit, never by a Medium."""
    before = slugs(SOLVE, limit=3)
    after = slugs(SOLVE, solved=frozenset(EASY[:1]), limit=3)

    assert before == list(EASY[:3])
    assert after == list(EASY[1:4])
    assert not set(after) & set(MEDIUM)


def test_a_solve_in_the_last_three_shrinks_the_list_and_never_backfills():
    """Two of three left, one solved: one row, not a Medium in the gap."""
    done = frozenset(EASY[2:]) | {EASY[0]}

    assert slugs(SOLVE, solved=done) == [EASY[1]]


def test_theory_still_lists_the_whole_unit_in_pool_order():
    """THEORY is untouched: every difficulty of u, in the order the pool ranked them."""
    expected = [p.title_slug for p in pool().problems if p.topics == ("prefix-sum",)]

    assert slugs(THEORY) == expected
    assert set(MEDIUM) <= set(expected)


def test_none_and_an_unknown_phase_show_the_whole_list():
    """Every unit finished, or no phase read: the screen as it was."""
    whole = [p.title_slug for p in pool().problems]

    assert slugs(NONE) == whole
    assert slugs(None) == whole


def test_solve_without_a_curriculum_keeps_the_whole_list():
    """No blocks means no unit membership to filter by: never an empty list."""
    bare = PoolResolution(problems=pool().problems, source="cache", notes=())

    assert slugs(SOLVE, the_pool=bare) == [p.title_slug for p in bare.problems]


def test_no_easy_left_while_solve_holds_falls_back_to_todays_unit_rows(caplog):
    """The set is empty but SOLVE holds: today's narrowing, and a warning."""
    with caplog.at_level(logging.WARNING, logger=_viewmodel_lines.__name__):
        rows = slugs(SOLVE, solved=frozenset(EASY))

    assert rows == [PREMIUM, *MEDIUM, *HARD]
    assert [r.levelno for r in caplog.records] == [logging.WARNING]
    assert "prefix-sums" in caplog.records[0].getMessage()


def test_the_fallback_warns_once_per_unit_not_once_per_repaint(caplog):
    """A repaint runs every poll: a stale cache must not flood the journal."""
    done = frozenset(EASY)
    with caplog.at_level(logging.WARNING, logger=_viewmodel_lines.__name__):
        slugs(SOLVE, solved=done)
        slugs(SOLVE, solved=done)
        slugs(SOLVE)  # the set refills: the latch resets
        slugs(SOLVE, solved=done)

    assert len(caplog.records) == 2


def test_a_unit_with_no_rows_at_all_falls_back_to_the_whole_list():
    """Nothing of u anywhere: the whole pool, so an Open button remains."""
    other = PoolResolution(
        problems=tuple(make(s, topics=["stack"]) for s in STACK_EASY),
        source="cache",
        notes=(),
        blocks=unit_pool().blocks,
    )

    assert slugs(SOLVE, the_pool=other) == list(STACK_EASY)


def test_solved_easy_are_acknowledged_by_title():
    """The titles of the solved Easy still come back for the status line."""
    _, dropped = build_problem_lines(
        pool(),
        limit=99,
        unit="prefix-sums",
        solved_slugs=frozenset(EASY[:2]),
        easy_only=True,
    )

    assert dropped == tuple(make(s).title for s in EASY[:2])


def test_the_phase_screen_says_when_only_easy_rows_apply():
    """``easy_only`` is true in SOLVE of a known unit, and nowhere else."""
    assert build_phase_screen(SOLVE).easy_only
    assert not build_phase_screen(THEORY).easy_only
    assert not build_phase_screen(NONE).easy_only
    assert not build_phase_screen(None).easy_only
    assert PHASE_ROWS == 5
