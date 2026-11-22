"""The strip's dot grid: bigger dots, a visible gap, wrapping, nothing dropped."""

from __future__ import annotations

import pytest

from leetcode_guard._constants import STUDY_STRIP_WIDTH_PX
from leetcode_guard._strip_dots import (
    BUDGET_PX,
    MIN_GAP_PX,
    MIN_PX,
    PAD_PX,
    layout,
)

CASES = [(0, 0), (1, 6), (0, 7), (3, 12), (8, 20)]
"""earned + owed, as kuhy listed them."""


@pytest.mark.parametrize(("earned", "owed"), CASES)
def test_every_dot_is_drawn_filled_first_then_hollow(earned: int, owed: int):
    """Filled dots lead, then the hollow ones, none dropped."""
    grid = layout(earned, owed, width=STUDY_STRIP_WIDTH_PX)

    assert [d.filled for d in grid.dots] == [True] * earned + [False] * owed


@pytest.mark.parametrize(("earned", "owed"), CASES[1:])
def test_nothing_is_clipped_and_dots_do_not_touch(earned: int, owed: int):
    """Inside the width and the height, a visible gap between any two dots."""
    grid = layout(earned, owed, width=STUDY_STRIP_WIDTH_PX)
    size, gap = grid.diameter, grid.gap

    assert gap >= MIN_GAP_PX
    assert all(d.x >= 0 and d.x + size <= STUDY_STRIP_WIDTH_PX for d in grid.dots)
    assert all(d.y >= PAD_PX and d.y + size + PAD_PX <= grid.height for d in grid.dots)
    for a in grid.dots:
        for b in grid.dots:
            if a is not b:
                assert abs(a.x - b.x) >= size + gap or abs(a.y - b.y) >= size + gap


@pytest.mark.parametrize(("earned", "owed"), [(1, 6), (0, 7)])
def test_a_normal_row_is_clearly_larger_than_the_old_glyph(earned: int, owed: int):
    """The old row was a 16 px glyph; the new dots are at least 24 px on one row."""
    grid = layout(earned, owed, width=STUDY_STRIP_WIDTH_PX)

    assert grid.diameter >= 24
    assert len({d.y for d in grid.dots}) == 1


def test_many_dots_wrap_onto_rows_within_the_budget():
    """3+12 and 8+20 wrap and stay inside the height budget at a legible size."""
    for earned, owed in ((3, 12), (8, 20)):
        grid = layout(earned, owed, width=STUDY_STRIP_WIDTH_PX)

        assert len({d.y for d in grid.dots}) > 1
        assert grid.height <= BUDGET_PX + 2 * PAD_PX
        assert grid.diameter >= 16


def test_a_flood_of_dots_grows_the_strip_instead_of_dropping_any():
    """Past the budget at the smallest dot the grid gets taller; no dot is lost."""
    grid = layout(200, 400, width=STUDY_STRIP_WIDTH_PX)

    assert len(grid.dots) == 600
    assert grid.diameter == MIN_PX
    assert grid.height > BUDGET_PX


def test_no_dots_is_an_empty_grid():
    """0+0 draws nothing; the caller shows the check."""
    grid = layout(0, 0, width=STUDY_STRIP_WIDTH_PX)

    assert grid.dots == ()
    assert grid.height == 0
