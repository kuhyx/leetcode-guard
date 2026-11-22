"""Review first falls open: a failed launch, the demo, a non-finite ``at``.

Each test is one failure the red-team found in the first cut of the rule. All of
them fail OPEN: the SOLVE rows show, the lock still arms and polls.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, NoReturn
from unittest.mock import MagicMock

import pytest

from leetcode_guard._lock_phase import DEMO_PHASE_ENV
from leetcode_guard._review_due import DueRead, DueStatus, check_due
from leetcode_guard.tests._guard_factories import probe_of
from leetcode_guard.tests._phase_fixtures import PREFIX
from leetcode_guard.tests._review_first_fixtures import (
    ROUTE,
    T_MS,
    TARGET,
    install_tutor,
    slugs_of,
    write_module_due,
)
from leetcode_guard.tests._review_first_fixtures import (
    review_guard as _guard,
)
from leetcode_guard.tests._tutor_fixtures import due_row, signed, write_due

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(name="tutor", autouse=True)
def _tutor(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return install_tutor(monkeypatch)


# -- B: a launch that fails must not leave a gate nobody can satisfy ------------


@pytest.fixture(name="failing_launch")
def _failing_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "leetcode_guard._lock_learn.launch_tutor",
        lambda _route: MagicMock(ok=False, reason="exit 127"),
    )


@pytest.mark.usefixtures("failing_launch")
def test_a_failed_review_launch_brings_the_solve_rows_back_for_the_run(
    tmp_path: Path,
    hmac_key: Path,
    caplog: pytest.LogCaptureFixture,
):
    """The first failed press falls open; the file still says due, the rows stay."""
    write_module_due(hmac_key, [T_MS - 1])
    guard = _guard(tmp_path, hmac_key)
    assert [line.url for line in guard.model.problems] == [ROUTE]

    with caplog.at_level(logging.WARNING):
        guard.open_problem(ROUTE)
        assert slugs_of(guard.model) == list(PREFIX)
        guard.open_problem(ROUTE)
        guard.open_problem(ROUTE)
        guard.on_poll_result(probe_of("old-1"))

    assert slugs_of(guard.model) == list(PREFIX)
    assert not guard.session().active
    fell = [r for r in caplog.records if "review" in r.getMessage()]
    assert len(fell) == 1


@pytest.mark.usefixtures("failing_launch")
def test_the_fall_open_repaints_the_surfaces_and_verifies_the_rows(
    tmp_path: Path, hmac_key: Path, monkeypatch
):
    """Same repaint path as "nothing due": painted rows, live check of the rows."""
    write_module_due(hmac_key, [T_MS - 1])
    guard = _guard(tmp_path, hmac_key)
    view = next(iter(guard.frames.views.values()))
    asked: list[int] = []
    monkeypatch.setattr(guard, "on_reveal", asked.append)

    guard.open_problem(ROUTE)

    assert view.phase.painted.review is None
    assert asked == [len(PREFIX)]


def test_a_successful_review_launch_keeps_the_rule(
    tmp_path: Path, hmac_key: Path, tutor: list[str]
):
    """Only a failure falls open: the study session runs and the review row stays."""
    write_module_due(hmac_key, [T_MS - 1])
    guard = _guard(tmp_path, hmac_key)

    guard.open_problem(ROUTE)
    guard.on_poll_result(probe_of("old-1"))

    assert tutor == [ROUTE]
    assert [line.url for line in guard.model.problems] == [ROUTE]


def test_a_missing_launcher_at_press_time_falls_open_too(
    tmp_path: Path, hmac_key: Path, monkeypatch
):
    """The launcher vanished between the read and the press: same fall-open."""
    write_module_due(hmac_key, [T_MS - 1])
    guard = _guard(tmp_path, hmac_key)
    monkeypatch.setattr("leetcode_guard._lock_learn.find_tutor", lambda: None)

    guard.open_problem(ROUTE)

    assert slugs_of(guard.model) == list(PREFIX)


# -- D: the demo never reads live tutor state -------------------------------


def _read_must_not_happen(*_args: object, **_kwargs: object) -> NoReturn:
    pytest.fail("the demo read the tutor's review_due.json")


def test_the_demo_never_reads_the_tutors_file(
    tmp_path: Path, hmac_key: Path, monkeypatch
):
    """A due file on disk is invisible in demo mode: the fixture says nothing due."""
    write_module_due(hmac_key, [T_MS - 1])
    monkeypatch.setattr("leetcode_guard._review_due.check_due", _read_must_not_happen)

    guard = _guard(tmp_path, hmac_key, demo_mode=True)
    guard.on_poll_result(probe_of("old-1"))

    assert guard.run_state.phases.review == DueRead(DueStatus.CLEAR)
    assert slugs_of(guard.model) == list(PREFIX)


def test_the_demo_fixture_screen_reads_nothing_either(
    tmp_path: Path, hmac_key: Path, monkeypatch
):
    """The screenshot route (``LEETCODE_GUARD_DEMO_PHASE=solve``) too."""
    write_module_due(hmac_key, [T_MS - 1])
    monkeypatch.setenv(DEMO_PHASE_ENV, "solve")
    monkeypatch.setattr("leetcode_guard._review_due.check_due", _read_must_not_happen)

    guard = _guard(tmp_path, hmac_key, demo_mode=True)

    assert guard.run_state.phases.review == DueRead(DueStatus.CLEAR)


# -- E: a non-finite ``at`` can never be superseded -------------------------


@pytest.mark.parametrize("at", [float("nan"), float("inf"), float("-inf"), 10**400])
def test_a_non_finite_at_is_a_malformed_detail_and_skipped(at: float, hmac_key: Path):
    """NaN/inf would win every ``at >=`` comparison, or lose all of them, for ever."""
    stuck = due_row("prefix-sums", [], at=10.0, key_file=hmac_key)
    stuck.pop("hmac")
    detail = stuck["detail"]
    assert isinstance(detail, dict)
    detail["at"] = at
    stuck = signed(stuck, hmac_key)
    later = due_row("prefix-sums", [T_MS - 1], at=20.0, key_file=hmac_key)

    for rows in ([stuck, later], [later, stuck]):
        write_due(rows)
        got = check_due((TARGET,), T_MS, key_file=hmac_key)
        assert got == DueRead(DueStatus.DUE, 1, TARGET)
