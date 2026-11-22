"""The lock reads the phase once per poll and repaints when it moves."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _glyphs as g
from leetcode_guard._lock_phase import DEMO_PHASE_ENV, demo_phase
from leetcode_guard._viewmodel_phase import NONE_SCREEN, build_phase_screen
from leetcode_guard.tests._guard_factories import probe_of
from leetcode_guard.tests._phase_fixtures import (
    NEXT,
    PREFIX,
    SOLVE,
    STACK,
    THEORY,
    unit_pool,
)
from leetcode_guard.tests.test_lock_study import locked_guard

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from leetcode_guard._phase_view import PhaseView


class _Script:
    """A phase source that walks a list, then repeats its last answer."""

    def __init__(self, *answers: PhaseView | Exception) -> None:
        self.answers = list(answers)
        self.calls = 0

    def __call__(self) -> PhaseView:
        self.calls += 1
        answer = self.answers[0] if len(self.answers) == 1 else self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def _guard(tmp_path: Path, hmac_key: Path, source: Callable[[], PhaseView] | None):
    return locked_guard(tmp_path, hmac_key, pool=unit_pool(), phase=source)


def _slugs(guard) -> list[str]:
    return [line.slug for line in guard.model.problems]


def test_the_first_screen_is_the_phase_read_before_the_window(
    tmp_path: Path, hmac_key: Path
):
    """THEORY from t=0: the card leads, the unit's problems follow."""
    guard = _guard(tmp_path, hmac_key, lambda: THEORY)

    assert guard.model.screen == build_phase_screen(THEORY)
    assert _slugs(guard) == list(PREFIX)


def test_theory_to_solve_to_the_next_unit_repaints_the_open_window(
    tmp_path: Path, hmac_key: Path
):
    """Module finished, then unit finished: two hand-overs, one poll each."""
    source = _Script(THEORY, SOLVE, NEXT)
    guard = _guard(tmp_path, hmac_key, source)
    view = next(iter(guard.frames.views.values()))

    guard.on_poll_result(probe_of("old-1"))
    assert guard.model.screen == build_phase_screen(SOLVE)
    assert view.phase.painted == build_phase_screen(SOLVE)
    assert _slugs(guard) == list(PREFIX)

    guard.on_poll_result(probe_of("old-1"))
    assert guard.model.screen == build_phase_screen(NEXT)
    assert view.phase.painted == build_phase_screen(NEXT)
    assert _slugs(guard) == list(STACK)


def test_one_read_per_poll_not_per_repaint(tmp_path: Path, hmac_key: Path):
    """Startup reads once; each poll once more, however often it repaints."""
    source = _Script(THEORY)
    guard = _guard(tmp_path, hmac_key, source)
    assert source.calls == 1

    guard.on_poll_result(probe_of("old-1"))
    guard.build_model(probe_of("old-1"))

    assert source.calls == 2


def test_a_failed_read_keeps_the_last_signed_screen(
    tmp_path: Path, hmac_key: Path, caplog
):
    """Cannot check is not "no": keep THEORY, log a warning, never raise."""
    guard = _guard(tmp_path, hmac_key, _Script(THEORY, OSError("unreadable")))

    with caplog.at_level(logging.WARNING):
        guard.on_poll_result(probe_of("old-1"))

    assert guard.model.screen == build_phase_screen(THEORY)
    assert "phase" in caplog.text


def test_no_source_or_a_failed_first_read_is_todays_list(
    tmp_path: Path, hmac_key: Path
):
    """Nothing ever read: the "none" screen, the whole pool."""
    for source in (None, _Script(RuntimeError("boom"))):
        guard = _guard(tmp_path / str(id(source)), hmac_key, source)
        assert guard.model.screen == NONE_SCREEN
        assert len(guard.model.problems) == len(unit_pool().problems)


def test_a_unit_change_verifies_the_rows_it_brings_on_screen(
    tmp_path: Path, hmac_key: Path, monkeypatch
):
    """The new unit's rows may sit below the pre-verified top of the pool."""
    asked: list[int] = []
    guard = _guard(tmp_path, hmac_key, _Script(THEORY, NEXT))
    monkeypatch.setattr(guard, "on_reveal", asked.append)

    guard.on_poll_result(probe_of("old-1"))

    assert asked == [len(STACK)]


@pytest.mark.parametrize("view", [THEORY, SOLVE])
def test_theory_and_solve_offer_open_the_hatch_and_break_glass_at_t0(
    tmp_path: Path, hmac_key: Path, tk_mock, view: PhaseView
):
    """The 2026-08-05 rule on both unit screens, from the first second."""
    guard = _guard(tmp_path, hmac_key, lambda: view)

    opens = [
        call
        for call in tk_mock.Button.call_args_list
        if call.kwargs.get("text") == g.OPEN
    ]
    assert guard.model.problems
    assert len(opens) == len(guard.model.problems)
    assert guard.should_offer_escape()
    surface = next(iter(guard.frames.views.values()))
    assert surface.decor.escape_button is not None
    assert surface.decor.breakglass is not None
    labels = [str(c.kwargs.get("text", "")) for c in tk_mock.Label.call_args_list]
    assert any("systemctl --user stop leetcode-guard.service" in t for t in labels)


@pytest.mark.parametrize("name", ["theory", "plan", "solve", "none"])
def test_the_demo_renders_each_screen_from_a_fixture(
    tmp_path: Path, hmac_key: Path, monkeypatch, name: str
):
    """``LEETCODE_GUARD_DEMO_PHASE`` picks the screen; the unit is the pool's first."""
    monkeypatch.setenv(DEMO_PHASE_ENV, name)
    guard = _guard(tmp_path, hmac_key, None)

    assert guard.model.screen == build_phase_screen(demo_phase(name, unit_pool()))
    expected = {"theory": "theory", "plan": "theory", "solve": "solve"}
    assert guard.model.screen.phase == expected.get(name, "none")
    if name != "none":
        assert guard.model.screen.unit == "stack-queue"


def test_the_demo_fixture_is_ignored_outside_the_demo(
    tmp_path: Path, hmac_key: Path, monkeypatch
):
    """The production lock never reads the env: only the rules side decides."""
    monkeypatch.setenv(DEMO_PHASE_ENV, "theory")
    guard = locked_guard(tmp_path, hmac_key, pool=unit_pool(), demo_mode=False)

    assert guard.model.screen == NONE_SCREEN


def test_an_unknown_demo_name_or_an_unranked_pool_is_still_drawable():
    """A typo is today's list; no curriculum gives an empty unit."""
    assert demo_phase("bogus", unit_pool()) is None
    fixture = demo_phase("theory", unit_pool(blocks=False))
    assert fixture is not None
    assert fixture.unit == ""
