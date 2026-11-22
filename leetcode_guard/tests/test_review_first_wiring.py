"""Where review first gets its modules and when it re-reads.

The unit view names the modules to check on SOLVE only; the phase reader asks
the tutor's file on every refresh and says when the review row left, so the
rows it brings back are verified like a unit change's.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from leetcode_guard._lock_phase import demo_phase
from leetcode_guard._review_due import DueStatus
from leetcode_guard.tests._phase_fixtures import SUBJECT, THEORY, unit_pool
from leetcode_guard.tests._review_first_fixtures import (
    SOLVE_R,
    T_MS,
    TARGET,
    write_module_due,
)
from leetcode_guard.tests._theory_scenario import states, taught, world
from leetcode_guard.tests._tutor_fixtures import ALGO
from leetcode_guard.tests.test_lock_study import locked_guard
from leetcode_guard.tests.test_unit_view import NOW, display_files, solved, view

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _tutor_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("leetcode_guard._lock_phase.find_tutor", lambda: "/x/tutor")


def test_solve_names_every_module_of_the_unit_theory_names_none(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """SOLVE(a): its one module; SOLVE(b): both, in order; THEORY(a): none."""
    world(tmp_path, monkeypatch)
    display_files()
    states(hmac_key, "a", "b1", "b2")
    solved(data_dir, hmac_key, "a1")
    assert view(data_dir, hmac_key).review_targets == ((ALGO, "b1"), (ALGO, "b2"))

    states(hmac_key, "a")
    solved(data_dir, hmac_key)
    taught(hmac_key, NOW, ("a", 30))
    assert view(data_dir, hmac_key).review_targets == ((ALGO, "a"),)

    states(hmac_key)
    assert view(data_dir, hmac_key).review_targets == ()


def test_the_demo_fixture_names_its_module_on_solve_only():
    """The screenshot demo reviews the pool's first unit, like its rework target."""
    solve = demo_phase("solve", unit_pool())
    theory = demo_phase("theory", unit_pool())

    assert solve is not None
    assert solve.review_targets == ((SUBJECT, solve.unit),)
    assert theory is not None
    assert theory.review_targets == ()


def _status(phases) -> DueStatus | None:
    return None if phases.review is None else phases.review.status


def test_the_reader_asks_on_every_refresh_and_says_when_review_left(
    tmp_path: Path, hmac_key: Path
):
    """True once, on the refresh that swaps the review row for the SOLVE rows."""
    write_module_due(hmac_key, [T_MS - 1])
    guard = locked_guard(
        tmp_path, hmac_key, pool=unit_pool(), phase=lambda: SOLVE_R, demo_mode=False
    )
    phases = guard.run_state.phases
    assert _status(phases) is DueStatus.DUE
    assert phases.review is not None
    assert phases.review.target == TARGET

    assert phases.refresh() is False

    write_module_due(hmac_key, [])
    assert phases.refresh() is True
    assert _status(phases) is DueStatus.CLEAR
    assert phases.refresh() is False


def test_off_solve_or_with_no_phase_there_is_nothing_to_review(
    tmp_path: Path, hmac_key: Path
):
    """THEORY, an unknown phase and a SOLVE with no module never read the file."""
    write_module_due(hmac_key, [T_MS - 1])
    for source in (
        lambda: replace(THEORY, review_targets=(TARGET,)),
        lambda: replace(SOLVE_R, review_targets=()),
        None,
    ):
        guard = locked_guard(
            tmp_path / str(id(source)),
            hmac_key,
            pool=unit_pool(),
            phase=source,
            demo_mode=False,
        )
        assert guard.run_state.phases.review is None
