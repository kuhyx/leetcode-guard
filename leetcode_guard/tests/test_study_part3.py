"""Continued from :mod:`leetcode_guard.tests.test_study_part2`, split for the 250-line cap."""

from __future__ import annotations

import logging
import tkinter as tk

import pytest

from leetcode_guard._study import StudyState, SuspendOutcome
from leetcode_guard.tests._study_fixtures import (
    DEMO,
    PRODUCTION,
    session,
    wired,
)


def test_a_watcher_that_will_not_restart_is_logged_not_raised(caplog):
    _parent, lock = wired()
    study = session(lock)
    study.suspend()
    lock._recovery.start.side_effect = tk.TclError("wedged")

    with caplog.at_level(logging.ERROR):
        outcome = study.resume()

    assert outcome.ok
    assert caplog.records


def test_a_refocus_failure_is_cosmetic(caplog):
    _parent, lock = wired()
    study = session(lock)
    study.suspend()
    lock.surfaces.focus_surface.side_effect = tk.TclError("no surface")

    with caplog.at_level(logging.WARNING):
        outcome = study.resume()

    assert outcome.ok
    assert "refocused" not in outcome.steps


def test_the_session_reports_whether_the_lock_is_stood_down():
    _parent, lock = wired()
    study = session(lock)

    assert study.active is False
    study.suspend()
    assert study.active is True
    study.resume()
    assert study.active is False


def test_elapsed_uses_the_injected_clock_and_is_zero_when_locked():
    _parent, lock = wired()
    study = session(lock, clock=[100.0, 142.0])

    assert study.elapsed_seconds() == 0.0
    study.suspend()
    assert study.elapsed_seconds() == 42.0


def test_the_outcome_carries_an_audit_trail():
    """ "Got halfway and then failed" is a real state, and naming the steps that
    completed makes it inspectable rather than inferred from a log."""
    _parent, lock = wired()

    outcome = session(lock).suspend()

    assert isinstance(outcome, SuspendOutcome)
    assert outcome.steps[0] == "recovery-stopped"
    assert outcome.steps[1] == "detector-stopped"
    assert "grab-released" in outcome.steps


def test_the_state_enum_says_what_it_means():
    assert StudyState.LOCKED.value == "locked"
    assert StudyState.STUDYING.value == "studying"


def test_a_non_tk_failure_mid_suspend_puts_the_lock_back(caplog):
    """The steps catch ``tk.TclError``, which is what window calls raise. This
    is the net under that: a wedged timer raising something else must not
    escape and leave the grab released while the state says LOCKED -- a
    silently unguarded machine is the exact failure this module exists to
    prevent."""
    _parent, lock = wired()
    # Fails *after* the grab is already released, so there is real state to
    # roll back rather than nothing to do.
    lock.surfaces.infos.side_effect = RuntimeError("gatelock blew up")

    with caplog.at_level(logging.ERROR):
        outcome = session(lock).suspend()

    assert outcome.ok is False
    assert "unexpectedly" in outcome.reason
    lock.root.grab_set_global.assert_called()
    lock._recovery.start.assert_called()
    assert caplog.records


def test_the_emergency_restore_leaves_the_session_locked():
    _parent, lock = wired()
    lock.surfaces.infos.side_effect = RuntimeError("boom")
    study = session(lock)

    study.suspend()

    assert study.active is False


def test_an_emergency_restore_step_that_also_fails_does_not_stop_the_rest(caplog):
    """It runs precisely when something already misbehaved, so raising again
    and abandoning the remaining steps is the one thing it must not do."""
    _parent, lock = wired()
    lock.surfaces.infos.side_effect = RuntimeError("boom")
    lock.root.deiconify.side_effect = RuntimeError("and again")

    with caplog.at_level(logging.ERROR):
        outcome = session(lock).suspend()

    assert outcome.ok is False
    # The later step still ran despite the earlier one throwing.
    lock._recovery.start.assert_called()


def test_the_emergency_restore_re_disables_vt():
    """A half-suspend must not leave VT switching handed back."""
    _parent, lock = wired()
    lock.surfaces.infos.side_effect = RuntimeError("boom")

    with pytest.MonkeyPatch.context() as patch:
        calls: list[str] = []
        patch.setattr(
            "leetcode_guard._study.disable_vt_switching", lambda: calls.append("vt")
        )
        session(lock, PRODUCTION).suspend()

    assert calls == ["vt"]


def test_a_regrab_that_never_succeeds_exhausts_its_attempts(caplog):
    """The bounded retry only closes the gap faster than the recovery tick; it
    is not the guarantee, so running out is a reported degradation and not a
    crash."""
    _parent, lock = wired()
    lock.root.grab_set_global.side_effect = tk.TclError("permanently held")
    told: list[str] = []
    study = session(lock, on_fail=told.append)
    study.suspend()

    with caplog.at_level(logging.ERROR):
        outcome = study.resume()

    assert outcome.ok is False
    assert told == ["the input grab could not be re-taken"]


def test_the_emergency_restore_leaves_vt_alone_in_demo():
    """Demo never disabled VT switching, so there is nothing to re-disable."""
    _parent, lock = wired()
    lock.surfaces.infos.side_effect = RuntimeError("boom")

    with pytest.MonkeyPatch.context() as patch:
        calls: list[str] = []
        patch.setattr(
            "leetcode_guard._study.disable_vt_switching", lambda: calls.append("vt")
        )
        session(lock, DEMO).suspend()

    assert calls == []
