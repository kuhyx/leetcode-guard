"""The learn button: study mode exactly like Open, then the tutor route (C4).

Same order as Open: find the launcher without spawning, suspend, spawn,
strip -- and a missing launcher never costs the grab.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from leetcode_guard import _glyphs as g
from leetcode_guard.tests._phase_fixtures import SUBJECT, THEORY, unit_pool
from leetcode_guard.tests.test_lock_study import locked_guard

if TYPE_CHECKING:
    from pathlib import Path

ROUTE = f"/learn/{SUBJECT}/prefix-sums"


@pytest.fixture(name="no_tutor_spawn")
def _no_tutor_spawn(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """A tutor launcher that always resolves and never actually runs."""
    launched: list[str] = []
    monkeypatch.setattr("leetcode_guard._lock_learn.find_tutor", lambda: "/x/tutor")

    def fake_launch(route: str) -> MagicMock:
        launched.append(route)
        return MagicMock(ok=True, reason="opened", command=())

    monkeypatch.setattr("leetcode_guard._lock_learn.launch_tutor", fake_launch)
    return launched


def _theory_guard(tmp_path: Path, hmac_key: Path, **kwargs):
    return locked_guard(
        tmp_path, hmac_key, pool=unit_pool(), phase=lambda: THEORY, **kwargs
    )


def _learn_marks(guard) -> list[str]:
    return [
        call.kwargs.get("text")
        for view in guard.frames.views.values()
        for call in view.phase.learn.configure.call_args_list
    ]


def test_learn_stands_the_lock_down_and_opens_the_route(
    tmp_path: Path, hmac_key: Path, no_tutor_spawn
):
    """Grab released, tutor asked for the module, strip up: Open's path."""
    guard = _theory_guard(tmp_path, hmac_key)

    guard.open_learn(ROUTE)

    guard.lock.root.grab_release.assert_called_once()
    assert no_tutor_spawn == [ROUTE]
    assert guard.session().active
    assert guard.strip is not None


def test_no_tutor_means_the_lock_is_never_weakened(
    tmp_path: Path, hmac_key: Path, monkeypatch, caplog
):
    """Missing launcher: no suspend, the button shows cannot-open, a warning."""
    monkeypatch.setattr("leetcode_guard._lock_learn.find_tutor", lambda: None)
    guard = _theory_guard(tmp_path, hmac_key)

    with caplog.at_level(logging.WARNING):
        guard.open_learn(ROUTE)

    guard.lock.recovery.stop.assert_not_called()
    guard.lock.root.grab_release.assert_not_called()
    assert not guard.session().active
    assert "tutor" in caplog.text
    assert g.NO_ENTRY in _learn_marks(guard)


def test_a_failed_tutor_launch_puts_the_lock_back(
    tmp_path: Path, hmac_key: Path, monkeypatch
):
    """Rollback after suspend, and the cannot-open mark on the button."""
    monkeypatch.setattr("leetcode_guard._lock_learn.find_tutor", lambda: "/x/tutor")
    monkeypatch.setattr(
        "leetcode_guard._lock_learn.launch_tutor",
        lambda _route: MagicMock(ok=False, reason="vanished", command=()),
    )
    guard = _theory_guard(tmp_path, hmac_key, demo_mode=False)

    guard.open_learn(ROUTE)

    assert not guard.session().active
    guard.lock.root.grab_set_global.assert_called()
    assert g.NO_ENTRY in _learn_marks(guard)


def test_a_raising_launcher_is_a_failed_launch(
    tmp_path: Path, hmac_key: Path, monkeypatch
):
    """Called with the grab released: nothing may escape the rollback."""
    monkeypatch.setattr("leetcode_guard._lock_learn.find_tutor", lambda: "/x/tutor")

    def explode(_route: str) -> None:
        raise RuntimeError

    monkeypatch.setattr("leetcode_guard._lock_learn.launch_tutor", explode)
    guard = _theory_guard(tmp_path, hmac_key)

    guard.open_learn(ROUTE)

    assert not guard.session().active


def test_learn_while_studying_does_not_re_suspend(
    tmp_path: Path, hmac_key: Path, no_tutor_spawn, no_spawn
):
    """Open a problem, then learn: one suspend, both launched."""
    guard = _theory_guard(tmp_path, hmac_key)
    guard.open_problem("https://leetcode.com/problems/range-sum/")

    guard.open_learn(ROUTE)

    guard.lock.root.grab_release.assert_called_once()
    assert no_spawn == ["https://leetcode.com/problems/range-sum/"]
    assert no_tutor_spawn == [ROUTE]


def test_the_surface_learn_button_is_wired_to_open_learn(
    tmp_path: Path, hmac_key: Path, no_tutor_spawn
):
    """The hook the surface gets is the lock's learn button."""
    guard = _theory_guard(tmp_path, hmac_key)
    view = next(iter(guard.frames.views.values()))

    view.hooks.on_learn(ROUTE)

    assert no_tutor_spawn == [ROUTE]
