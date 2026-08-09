"""Tests for study mode: the private-API pin and the suspend half.

Resume lives in ``test_study_part2.py``. Helpers in ``_study_fixtures``.
"""

from __future__ import annotations

import logging
import tkinter as tk

from leetcode_guard.tests._study_fixtures import (
    DEMO,
    PRODUCTION,
    index_of,
    session,
    wired,
)

# -- the gatelock private API this depends on ------------------------------


def test_the_private_gatelock_attributes_still_exist():
    """``_recovery``, ``_detector`` and ``SurfaceSet._surfaces`` have no public
    equivalent. Pinned to gatelock v0.4.0; if a bump renames one, this fails
    here rather than inside a live lock with the screen grabbed."""
    from gatelock import LockWindow
    from gatelock._surfaces import SurfaceSet

    assert "_recovery" in LockWindow.__init__.__code__.co_names
    assert "_detector" in LockWindow.__init__.__code__.co_names
    assert "_vt_disabled" in LockWindow.__init__.__code__.co_names
    assert "_surfaces" in SurfaceSet.__init__.__code__.co_names
    assert hasattr(SurfaceSet, "focus_surface")
    assert hasattr(SurfaceSet, "preferred_focus_index")
    # RecoveryLoop.holds_grab is the one *public* member reached through a
    # private handle, and the grab harness depends on it.
    from gatelock._recovery import RecoveryLoop

    assert hasattr(RecoveryLoop, "holds_grab")
    assert hasattr(RecoveryLoop, "stop")
    assert hasattr(RecoveryLoop, "start")


def test_every_private_gatelock_read_goes_through_the_adapter():
    """The coupling is deliberately concentrated in one file so it has exactly
    one place to audit and one lint exemption. If a study module starts reaching
    into gatelock directly again, that intent has been lost."""
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    private = {"_recovery", "_detector", "_vt_disabled", "_surfaces"}
    for name in ("_study.py", "_study_resume.py", "_lock_study.py"):
        # Parsed rather than grepped, so the module docstrings may go on
        # *naming* these attributes -- which they should -- without tripping it.
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        reached = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr in private
        }
        assert not reached, f"{name} reaches past the adapter: {sorted(reached)}"


# -- suspend ---------------------------------------------------------------


def test_suspend_stops_recovery_before_releasing_the_grab():
    """*The* regression test. With the loop still running the grab is re-taken
    within a tick, so the browser comes up focused and swallows every key --
    the original bug, wearing the fix as a disguise."""
    parent, lock = wired()

    session(lock).suspend()

    calls = parent.mock_calls
    assert index_of(calls, "lock._recovery.stop") < index_of(
        calls, "lock.root.grab_release"
    )


def test_suspend_stops_the_detector_too():
    """``_drain`` is scheduled independently of ``_verify``, so a live detector
    can still push a full tick through and undo everything."""
    parent, lock = wired()

    session(lock).suspend()

    calls = parent.mock_calls
    assert index_of(calls, "lock._detector.stop") < index_of(
        calls, "lock.root.grab_release"
    )


def test_suspend_releases_the_grab_because_hiding_surfaces_is_not_enough():
    """The grab lives on the root and is independent of stacking: withdrawing
    every surface would leave a browser that still receives nothing."""
    _parent, lock = wired()

    outcome = session(lock).suspend()

    lock.root.grab_release.assert_called_once()
    assert outcome.ok
    assert "grab-released" in outcome.steps


def test_suspend_withdraws_every_surface():
    _parent, lock = wired("DP-0", "HDMI-0")

    session(lock).suspend()

    for name in ("DP-0", "HDMI-0"):
        lock.surfaces._surfaces[name].window.withdraw.assert_called_once()
    lock.root.withdraw.assert_called_once()


def test_production_hands_back_vt_switching_and_demo_has_none_to_hand_back():
    _parent, lock = wired()
    outcome = session(lock, PRODUCTION).suspend()
    assert "vt-restored" in outcome.steps
    # gatelock's own flag must follow, or its close() skips the restore.
    assert lock._vt_disabled is False

    _parent2, lock2 = wired()
    assert "vt-restored" not in session(lock2, DEMO).suspend().steps


def test_a_grab_that_will_not_release_aborts_the_whole_suspend(caplog):
    """Refusing is the right answer: a browser we cannot type into is worse
    than no browser, and the lock is still fully asserted afterwards."""
    _parent, lock = wired()
    lock.root.grab_release.side_effect = tk.TclError("grab is held elsewhere")

    with caplog.at_level(logging.ERROR):
        outcome = session(lock).suspend()

    assert outcome.ok is False
    lock._recovery.start.assert_called_once()
    lock._detector.start.assert_called_once()
    lock.surfaces._surfaces["DP-0"].window.withdraw.assert_not_called()
    assert caplog.records


def test_a_recovery_loop_that_will_not_stop_aborts_before_the_grab(caplog):
    _parent, lock = wired()
    lock._recovery.stop.side_effect = tk.TclError("timer is wedged")

    with caplog.at_level(logging.ERROR):
        outcome = session(lock).suspend()

    assert outcome.ok is False
    lock.root.grab_release.assert_not_called()


def test_suspend_is_idempotent(caplog):
    _parent, lock = wired()
    study = session(lock)
    study.suspend()

    with caplog.at_level(logging.WARNING):
        second = study.suspend()

    assert second.ok
    assert second.reason == "already studying"
    lock.root.grab_release.assert_called_once()


def test_a_surface_that_will_not_withdraw_does_not_abort_the_others(caplog):
    _parent, lock = wired("DP-0", "HDMI-0")
    lock.surfaces._surfaces["DP-0"].window.withdraw.side_effect = tk.TclError("gone")

    with caplog.at_level(logging.WARNING):
        outcome = session(lock).suspend()

    assert outcome.ok
    lock.surfaces._surfaces["HDMI-0"].window.withdraw.assert_called_once()
    assert "surfaces-withdrawn:1" in outcome.steps


def test_a_root_that_will_not_withdraw_is_only_cosmetic(caplog):
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
    lock.surfaces._surfaces = {}

    outcome = session(lock).suspend()

    lock.root.grab_release.assert_called_once()
    assert outcome.ok


def test_a_surface_missing_from_the_set_is_skipped():
    _parent, lock = wired("DP-0")
    lock.surfaces._surfaces = {}

    outcome = session(lock).suspend()

    assert outcome.ok
    assert "surfaces-withdrawn:0" in outcome.steps


# -- the adapter -----------------------------------------------------------


def test_the_adapter_answers_whether_the_grab_is_held():
    """The question ``verify_study_grab`` asks on a real X server, and the one
    member here reached through a private handle but a *public* method."""
    from leetcode_guard._gatelock_internals import holds_grab

    _parent, lock = wired()
    lock._recovery.holds_grab.return_value = True
    assert holds_grab(lock) is True

    lock._recovery.holds_grab.return_value = False
    assert holds_grab(lock) is False


def test_the_adapter_skips_a_surface_missing_from_the_private_map():
    """A surface we cannot find is one we cannot hide, and the grab being
    released is the part that matters."""
    from leetcode_guard._gatelock_internals import surface_windows

    _parent, lock = wired("DP-0", "HDMI-0")
    del lock.surfaces._surfaces["DP-0"]

    found = [info.output_name for info, _window in surface_windows(lock)]

    assert found == ["HDMI-0"]
