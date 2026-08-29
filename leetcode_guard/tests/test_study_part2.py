"""Tests for study mode: putting the lock back.

The suspend half is in ``test_study.py``; helpers in ``_study_fixtures``.
"""

from __future__ import annotations

import logging
import tkinter as tk

import pytest

from leetcode_guard.tests._study_fixtures import (
    DEMO,
    index_of,
    session,
    wired,
)


def test_resume_sets_overrideredirect_before_deiconify():
    """``_enforce_one`` does it the other way round, which is why resume must
    not delegate to it: set after mapping, override-redirect is ignored and the
    surface comes back WM-managed and mis-placed."""
    parent, lock = wired()
    study = session(lock)
    study.suspend()
    parent.reset_mock()

    study.resume()

    calls = parent.mock_calls
    assert index_of(calls, "surf_DP-0.overrideredirect") < index_of(
        calls, "surf_DP-0.deiconify"
    )


def test_resume_maps_the_root_before_re_grabbing():
    """X refuses to grab for a withdrawn window."""
    parent, lock = wired()
    study = session(lock)
    study.suspend()
    parent.reset_mock()

    study.resume()

    calls = parent.mock_calls
    assert index_of(calls, "lock.root.deiconify") < index_of(
        calls, "lock.root.grab_set_global"
    )


def test_resume_re_disables_vt_before_taking_the_grab():
    """Strengthen first, so a grab that fails does not also hand back VT."""
    parent, lock = wired()
    study = session(lock)
    study.suspend()
    parent.reset_mock()

    with pytest.MonkeyPatch.context() as patch:
        calls: list[str] = []

        def fake_disable_vt() -> None:
            calls.append("vt")
            parent.vt_disabled()

        patch.setattr("leetcode_guard._study.disable_vt_switching", fake_disable_vt)
        study.resume()

    ordering = parent.mock_calls
    assert index_of(ordering, "vt_disabled") < index_of(
        ordering, "lock.root.grab_set_global"
    )


def test_resume_restores_the_surfaces_before_attempting_the_grab():
    """So there is never a moment where the screen is clear and the state says
    locked. A degraded lock still looks like a lock."""
    parent, lock = wired()
    study = session(lock)
    study.suspend()
    parent.reset_mock()

    study.resume()

    calls = parent.mock_calls
    assert index_of(calls, "surf_DP-0.deiconify") < index_of(
        calls, "lock.root.grab_set_global"
    )


def test_a_failed_regrab_still_restarts_recovery_and_reports(caplog):
    """The fail-closed proof. The recovery loop is the real guarantee -- it
    re-takes the grab the moment it frees up -- so it must be restarted even
    when, especially when, our own attempts failed."""
    _parent, lock = wired()
    lock.root.grab_set_global.side_effect = tk.TclError("someone else has it")
    told: list[str] = []
    study = session(lock, on_fail=told.append)
    study.suspend()

    with caplog.at_level(logging.ERROR):
        outcome = study.resume()

    assert outcome.ok is False
    lock._recovery.start.assert_called_once()
    lock._detector.start.assert_called_once()
    assert told == ["the input grab could not be re-taken"]
    assert study.active is False


def test_a_failed_regrab_leaves_every_surface_visible():
    """No half-state: the user sees a full lock screen either way."""
    _parent, lock = wired("DP-0", "HDMI-0")
    lock.root.grab_set_global.side_effect = tk.TclError("held")
    study = session(lock)
    study.suspend()
    for name in ("DP-0", "HDMI-0"):
        lock.surfaces._surfaces[name].window.reset_mock()

    study.resume()

    for name in ("DP-0", "HDMI-0"):
        window = lock.surfaces._surfaces[name].window
        window.deiconify.assert_called_once()
        window.withdraw.assert_not_called()


def test_a_local_grab_needs_no_re_grab():
    """Demo never took a global grab, so there is nothing to take back."""
    _parent, lock = wired()
    study = session(lock, DEMO)
    study.suspend()

    outcome = study.resume()

    lock.root.grab_set_global.assert_not_called()
    assert outcome.ok


def test_resume_refocuses_because_on_focus_ready_never_fires_twice():
    _parent, lock = wired()
    study = session(lock)
    study.suspend()

    outcome = study.resume()

    lock.surfaces.focus_surface.assert_called_once()
    assert "refocused" in outcome.steps


def test_resume_is_idempotent(caplog):
    _parent, lock = wired()
    study = session(lock)

    with caplog.at_level(logging.WARNING):
        outcome = study.resume()

    assert outcome.ok
    assert outcome.reason == "not studying"
    lock.root.grab_set_global.assert_not_called()


def test_a_surface_that_will_not_come_back_does_not_stop_the_rest(caplog):
    _parent, lock = wired("DP-0", "HDMI-0")
    study = session(lock)
    study.suspend()
    lock.surfaces._surfaces["DP-0"].window.deiconify.side_effect = tk.TclError("gone")

    with caplog.at_level(logging.WARNING):
        study.resume()

    lock.surfaces._surfaces["HDMI-0"].window.deiconify.assert_called_once()


def test_a_root_that_will_not_map_still_attempts_the_grab(caplog):
    _parent, lock = wired()
    study = session(lock)
    study.suspend()
    lock.root.deiconify.side_effect = tk.TclError("nope")

    with caplog.at_level(logging.WARNING):
        study.resume()

    lock.root.grab_set_global.assert_called()
