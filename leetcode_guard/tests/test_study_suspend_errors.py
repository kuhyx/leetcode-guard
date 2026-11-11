"""Tests for study-mode suspend when a step fails or the surface set is odd.

The happy path and the private-API pin live in ``test_study.py``. ``wired()``
hangs each surface window off the parent mock as ``surf_<output>``.
"""

from __future__ import annotations

import logging
import tkinter as tk

from leetcode_guard._gatelock_internals import set_surface_map
from leetcode_guard.tests._study_fixtures import session, wired


def test_a_grab_that_will_not_release_aborts_the_whole_suspend(caplog):
    """Refusing is the right answer: a browser we cannot type into is worse
    than no browser, and the lock is still fully asserted afterwards."""
    parent, lock = wired()
    lock.root.grab_release.side_effect = tk.TclError("grab is held elsewhere")

    with caplog.at_level(logging.ERROR):
        outcome = session(lock).suspend()

    assert outcome.ok is False
    lock.recovery.start.assert_called_once()
    lock.detector.start.assert_called_once()
    getattr(parent, "surf_DP-0").withdraw.assert_not_called()
    assert caplog.records


def test_a_recovery_loop_that_will_not_stop_aborts_before_the_grab(caplog):
    """A recovery loop that refuses to stop means the grab is never released."""
    _parent, lock = wired()
    lock.recovery.stop.side_effect = tk.TclError("timer is wedged")

    with caplog.at_level(logging.ERROR):
        outcome = session(lock).suspend()

    assert outcome.ok is False
    lock.root.grab_release.assert_not_called()


def test_suspend_is_idempotent(caplog):
    """A second suspend reports "already studying" and releases nothing again."""
    _parent, lock = wired()
    study = session(lock)
    study.suspend()

    with caplog.at_level(logging.WARNING):
        second = study.suspend()

    assert second.ok
    assert second.reason == "already studying"
    lock.root.grab_release.assert_called_once()


def test_a_surface_that_will_not_withdraw_does_not_abort_the_others(caplog):
    """One surface failing to withdraw still lets the remaining ones hide."""
    parent, lock = wired("DP-0", "HDMI-0")
    getattr(parent, "surf_DP-0").withdraw.side_effect = tk.TclError("gone")

    with caplog.at_level(logging.WARNING):
        outcome = session(lock).suspend()

    assert outcome.ok
    getattr(parent, "surf_HDMI-0").withdraw.assert_called_once()
    assert "surfaces-withdrawn:1" in outcome.steps


def test_a_root_that_will_not_withdraw_is_only_cosmetic(caplog):
    """A root that will not withdraw still leaves the suspend successful."""
    _parent, lock = wired()
    lock.root.withdraw.side_effect = tk.TclError("nope")

    with caplog.at_level(logging.WARNING):
        outcome = session(lock).suspend()

    assert outcome.ok
    assert "root-withdrawn" not in outcome.steps


def test_zero_live_outputs_still_releases_the_grab():
    """With no surface the user cannot see the lock anyway; the grab is the
    only thing still trapping them."""
    _parent, lock = wired()
    lock.surfaces.infos.return_value = ()
    set_surface_map(lock.surfaces, {})

    outcome = session(lock).suspend()

    lock.root.grab_release.assert_called_once()
    assert outcome.ok


def test_a_surface_missing_from_the_set_is_skipped():
    """An output with no entry in the surface map is skipped, not an error."""
    _parent, lock = wired("DP-0")
    set_surface_map(lock.surfaces, {})

    outcome = session(lock).suspend()

    assert outcome.ok
    assert "surfaces-withdrawn:0" in outcome.steps
