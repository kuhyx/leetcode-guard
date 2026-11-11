"""Tests for study mode: the private-API pin and the suspend half.

Resume lives in ``test_study_part2.py``, failing suspend steps in
``test_study_suspend_errors.py``. Helpers in ``_study_fixtures``.
"""

from __future__ import annotations

import ast
import pathlib

from gatelock import LockWindow
from gatelock._recovery import RecoveryLoop
from gatelock._surfaces import SurfaceSet

from leetcode_guard._gatelock_internals import (
    holds_grab,
    surface_map,
    surface_windows,
    vt_disabled,
)
from leetcode_guard.tests._study_fixtures import (
    DEMO,
    PRODUCTION,
    index_of,
    session,
    wired,
)

# -- the gatelock private API this depends on ------------------------------


def test_the_private_gatelock_attributes_still_exist():
    """``_vt_disabled``, ``_arming`` and ``SurfaceSet._surfaces`` have no public equivalent
    (``recovery`` / ``detector`` became public in gatelock 0.8.1). If a bump
    renames one, this fails here rather than inside a live lock with the
    screen grabbed."""
    assert isinstance(LockWindow.recovery, property)
    assert isinstance(LockWindow.detector, property)
    assert "_vt_disabled" in LockWindow.__init__.__code__.co_names
    assert "_arming" in LockWindow.__init__.__code__.co_names
    assert "_surfaces" in SurfaceSet.__init__.__code__.co_names
    assert hasattr(SurfaceSet, "focus_surface")
    assert hasattr(SurfaceSet, "preferred_focus_index")
    # RecoveryLoop's members the study adapter and the grab harness call.
    assert hasattr(RecoveryLoop, "holds_grab")
    assert hasattr(RecoveryLoop, "stop")
    assert hasattr(RecoveryLoop, "start")


def test_every_private_gatelock_read_goes_through_the_adapter():
    """The coupling is deliberately concentrated in one file so it has exactly
    one place to audit and one lint exemption. If a study module starts reaching
    into gatelock directly again, that intent has been lost."""
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
    assert index_of(calls, "lock.recovery.stop") < index_of(
        calls, "lock.root.grab_release"
    )


def test_suspend_stops_the_detector_too():
    """``_drain`` is scheduled independently of ``_verify``, so a live detector
    can still push a full tick through and undo everything."""
    parent, lock = wired()

    session(lock).suspend()

    calls = parent.mock_calls
    assert index_of(calls, "lock.detector.stop") < index_of(
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
    """Suspend withdraws every output's surface window and the root."""
    parent, lock = wired("DP-0", "HDMI-0")

    session(lock).suspend()

    # wired() hangs each surface window off the parent as ``surf_<output>``.
    for name in ("DP-0", "HDMI-0"):
        getattr(parent, f"surf_{name}").withdraw.assert_called_once()
    lock.root.withdraw.assert_called_once()


def test_production_hands_back_vt_switching_and_demo_has_none_to_hand_back():
    """Production restores VT switching on suspend; demo never disabled it."""
    _parent, lock = wired()
    outcome = session(lock, PRODUCTION).suspend()
    assert "vt-restored" in outcome.steps
    # gatelock's own flag must follow, or its close() skips the restore.
    assert vt_disabled(lock) is False

    _parent2, lock2 = wired()
    assert "vt-restored" not in session(lock2, DEMO).suspend().steps


# -- the adapter -----------------------------------------------------------


def test_the_adapter_answers_whether_the_grab_is_held():
    """The question ``verify_study_grab`` asks on a real X server, and the one
    member here reached through a private handle but a *public* method."""
    _parent, lock = wired()
    lock.recovery.holds_grab.return_value = True
    assert holds_grab(lock) is True

    lock.recovery.holds_grab.return_value = False
    assert holds_grab(lock) is False


def test_the_adapter_skips_a_surface_missing_from_the_private_map():
    """A surface we cannot find is one we cannot hide, and the grab being
    released is the part that matters."""
    _parent, lock = wired("DP-0", "HDMI-0")
    del surface_map(lock.surfaces)["DP-0"]

    found = [info.output_name for info, _window in surface_windows(lock)]

    assert found == ["HDMI-0"]
