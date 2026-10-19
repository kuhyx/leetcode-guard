"""Tests for study mode keeping gatelock's ``Claim.grab_held`` truthful.

leisure-watch pauses billing only while a locker's X grab is actually held
(gatelock 0.11 ``held_grabs``). Study mode releases the grab with the claim
still live, so it must say so: False *before* the release (fail closed -- a
reader never sees "held" for a grab that is already gone), True only after a
re-grab that worked. Helpers in ``_study_fixtures``.
"""

from __future__ import annotations

import tkinter as tk
from unittest.mock import call

from leetcode_guard.tests._study_fixtures import DEMO, index_of, session, wired


def test_suspend_reports_not_held_before_releasing_the_grab():
    """The claim says "released" before the grab actually goes."""
    parent, lock = wired()

    session(lock).suspend()

    calls = parent.mock_calls
    assert index_of(calls, "lock.report_grab_held") < index_of(
        calls, "lock.root.grab_release"
    )
    lock.report_grab_held.assert_called_once_with(held=False)


def test_a_grab_that_will_not_release_reports_held_again():
    """Rolled back: the grab never left, so the claim must not say it did."""
    _parent, lock = wired()
    lock.root.grab_release.side_effect = tk.TclError("stuck")

    assert not session(lock).suspend().ok

    assert lock.report_grab_held.call_args_list == [
        call(held=False),
        call(held=True),
    ]


def test_resume_reports_held_only_after_the_grab_lands():
    """True comes after grab_set_global returned, not before."""
    parent, lock = wired()
    study = session(lock)
    study.suspend()
    parent.reset_mock()

    assert study.resume().ok

    calls = parent.mock_calls
    assert index_of(calls, "lock.root.grab_set_global") < index_of(
        calls, "lock.report_grab_held"
    )
    lock.report_grab_held.assert_called_once_with(held=True)


def test_a_failed_regrab_never_reports_held():
    """Degraded lock: the recovery loop reports True once it heals it."""
    _parent, lock = wired()
    study = session(lock)
    study.suspend()
    lock.report_grab_held.reset_mock()
    lock.root.grab_set_global.side_effect = tk.TclError("browser has it")

    assert not study.resume().ok

    lock.report_grab_held.assert_not_called()


def test_a_local_grab_lock_is_not_reported_held_after_resume():
    """Study mode does not re-take a local grab, so it is not held."""
    _parent, lock = wired()
    study = session(lock, DEMO)
    study.suspend()
    lock.report_grab_held.reset_mock()

    study.resume()

    lock.report_grab_held.assert_not_called()
