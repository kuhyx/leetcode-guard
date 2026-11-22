"""What the lock does when the tutor launcher exits non-zero (``_lock_learn``).

The launch is detached; ``_launch_watch`` reports the exit. A failure ends the
study mode the press opened (grab back, strip gone, marker forgotten) only if
that session is still the one running; a review falls open either way.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from leetcode_guard import _glyphs as g
from leetcode_guard._browser import LaunchResult
from leetcode_guard.tests._phase_fixtures import SUBJECT, THEORY, unit_pool
from leetcode_guard.tests.test_lock_study import locked_guard

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

LEARN = f"/learn/{SUBJECT}/prefix-sums"
REVIEW = f"/review/{SUBJECT}/prefix-sums"
PROC = object()


@pytest.fixture(name="watched")
def _watched(monkeypatch: pytest.MonkeyPatch) -> list[Callable[[int], None]]:
    """A tutor that starts; the watch's failure callback, captured per press."""
    callbacks: list[Callable[[int], None]] = []
    monkeypatch.setattr("leetcode_guard._lock_learn.find_tutor", lambda: "/x/tutor")
    monkeypatch.setattr(
        "leetcode_guard._lock_learn.launch_tutor",
        lambda _route: LaunchResult(ok=True, reason="opened", process=PROC),
    )

    def watch(_after: object, process: object, on_failure) -> bool:
        assert process is PROC
        callbacks.append(on_failure)
        return True

    monkeypatch.setattr("leetcode_guard._lock_learn.watch_exit", watch)
    return callbacks


def _guard(tmp_path: Path, hmac_key: Path):
    guard = locked_guard(
        tmp_path, hmac_key, pool=unit_pool(), phase=lambda: THEORY, demo_mode=False
    )
    guard.fall_open_review = MagicMock()
    return guard


def _learn_marks(guard) -> list[str]:
    return [
        call.kwargs.get("text")
        for view in guard.frames.views.values()
        for call in view.phase.learn.configure.call_args_list
    ]


def test_a_learn_launcher_that_exits_1_puts_the_lock_back(
    tmp_path: Path, hmac_key: Path, watched
):
    """Its own session still runs: Back to lock, the no-entry glyph, no fall-open."""
    guard = _guard(tmp_path, hmac_key)

    assert guard.open_learn(LEARN)
    assert guard.session().active
    watched[0](1)

    assert not guard.session().active
    assert guard.strip is None
    guard.lock.root.grab_set_global.assert_called()
    assert g.NO_ENTRY in _learn_marks(guard)
    guard.fall_open_review.assert_not_called()


def test_a_review_launcher_that_exits_1_falls_open(
    tmp_path: Path, hmac_key: Path, watched
):
    """The review row cannot be satisfied by a tutor that will not start."""
    guard = _guard(tmp_path, hmac_key)

    guard.open_learn(REVIEW)
    watched[0](2)

    assert not guard.session().active
    guard.fall_open_review.assert_called_once()


def test_after_back_to_lock_a_late_failure_only_reports(
    tmp_path: Path, hmac_key: Path, watched
):
    """Nothing to undo: the status line, never the glyph or a second relock."""
    guard = _guard(tmp_path, hmac_key)
    guard.open_learn(LEARN)
    guard.back_to_lock()
    view = next(iter(guard.frames.views.values()))
    view.status_line.configure.reset_mock()

    watched[0](1)

    assert g.NO_ENTRY not in _learn_marks(guard)
    assert view.status_line.configure.call_args.kwargs["text"] == g.BLIND


def test_a_failure_from_an_earlier_press_leaves_a_later_session_alone(
    tmp_path: Path, hmac_key: Path, watched
):
    """Back, then learn again: the first launcher's exit must not end the second."""
    guard = _guard(tmp_path, hmac_key)
    guard.open_learn(LEARN)
    guard.back_to_lock()
    guard.open_learn(LEARN)

    watched[0](1)

    assert guard.session().active


def test_no_watch_when_the_lock_could_not_stand_down(
    tmp_path: Path, hmac_key: Path, watched, monkeypatch
):
    """A refused suspend spawns nothing, so there is nothing to watch."""
    guard = _guard(tmp_path, hmac_key)
    monkeypatch.setattr(
        guard.session(), "suspend", lambda: MagicMock(ok=False, reason="no")
    )

    assert guard.open_learn(LEARN)
    assert watched == []
