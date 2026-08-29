"""Tests for the study-mode wiring: Open, the strip, and the ways back.

The ordering that matters here is "browser first, grab second" -- discovering
there is no browser *after* standing the lock down would leave the machine
unguarded for nothing.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from leetcode_guard.tests._guard_factories import create_guard, probe_of

if TYPE_CHECKING:
    from pathlib import Path

URL = "https://leetcode.com/problems/two-sum/"


def locked_guard(tmp_path: Path, hmac_key: Path, **kwargs):
    """A guard on an ordinary gating day.

    ``_recovery`` and ``_detector`` are real gatelock objects here, driving real
    ``after`` timers off a mocked root. Study mode only ever calls ``stop`` and
    ``start`` on them, so swapping in mocks keeps the assertions readable and
    stops a live timer outliving the test.
    """
    guard, _ = create_guard(
        tmp_path, probe=probe_of("old-1"), key_file=hmac_key, seeded=True, **kwargs
    )
    guard._lock._recovery = MagicMock()
    guard._lock._detector = MagicMock()
    return guard


def test_open_stands_the_lock_down_and_launches(
    tmp_path: Path, hmac_key: Path, no_spawn
):
    """The whole point: the grab has to come off or the browser gets no keys."""
    guard = locked_guard(tmp_path, hmac_key)

    guard._open_problem(URL)

    guard._lock.root.grab_release.assert_called_once()
    assert no_spawn == [URL]
    assert guard._session().active


def test_no_browser_means_the_lock_is_never_weakened(
    tmp_path: Path, hmac_key: Path, monkeypatch
):
    """The common failure -- nothing installed -- must not cost the grab."""
    monkeypatch.setattr("leetcode_guard._lock_study.find_opener", lambda: None)
    guard = locked_guard(tmp_path, hmac_key)

    guard._open_problem(URL)

    guard._lock._recovery.stop.assert_not_called()
    guard._lock.root.grab_release.assert_not_called()
    assert not guard._session().active
    for view in guard._views.values():
        view.status_line.configure.assert_called()


def test_a_failed_suspend_does_not_launch_a_browser(
    tmp_path: Path, hmac_key: Path, no_spawn
):
    """A browser we cannot type into is worse than none: refuse instead."""
    guard = locked_guard(tmp_path, hmac_key)
    guard._lock.root.grab_release.side_effect = tk.TclError("held elsewhere")

    guard._open_problem(URL)

    assert no_spawn == []
    assert not guard._session().active


def test_a_failed_launch_after_suspend_puts_the_lock_back(
    tmp_path: Path, hmac_key: Path, monkeypatch
):
    """Rollback: never leave the machine open with nothing to study on."""
    monkeypatch.setattr(
        "leetcode_guard._lock_study.find_opener", lambda: "/usr/bin/xdg-open"
    )
    monkeypatch.setattr(
        "leetcode_guard._lock_study.launch",
        lambda _url: MagicMock(ok=False, reason="vanished", command=()),
    )
    guard = locked_guard(tmp_path, hmac_key, demo_mode=False)

    guard._open_problem(URL)

    assert not guard._session().active
    guard._lock.root.grab_set_global.assert_called()


def test_a_second_problem_while_studying_does_not_re_suspend(
    tmp_path: Path, hmac_key: Path, no_spawn
):
    """Opening another problem mid-session is legitimate and must tear nothing
    down -- including the elapsed clock."""
    guard = locked_guard(tmp_path, hmac_key)
    guard._open_problem(URL)
    other = "https://leetcode.com/problems/valid-parentheses/"

    guard._open_problem(other)

    guard._lock.root.grab_release.assert_called_once()
    guard._lock._recovery.stop.assert_called_once()
    assert no_spawn == [URL, other]


def test_the_strip_goes_up_on_the_primary_output(
    tmp_path: Path, hmac_key: Path, no_spawn
):
    guard = locked_guard(tmp_path, hmac_key)

    guard._open_problem(URL)

    assert guard._strip is not None


def test_no_output_means_no_strip_but_study_still_runs(
    tmp_path: Path, hmac_key: Path, no_spawn
):
    """Zero live outputs: the poller still watches and a real solve still
    unlocks, so this is degraded rather than broken."""
    guard = locked_guard(tmp_path, hmac_key)
    # `surfaces` is a real read-only property on LockWindow, so the whole
    # surface set is swapped rather than one return value.
    guard._lock._surfaces = MagicMock()
    guard._lock._surfaces.infos.return_value = ()
    guard._lock._surfaces._surfaces = {}

    guard._open_problem(URL)

    assert guard._strip is None
    assert guard._session().active


def test_back_to_lock_re_grabs_and_drops_the_strip(
    tmp_path: Path, hmac_key: Path, no_spawn
):
    guard = locked_guard(tmp_path, hmac_key, demo_mode=False)
    guard._open_problem(URL)
    strip = guard._strip

    guard._back_to_lock()

    guard._lock.root.grab_set_global.assert_called()
    strip.window.destroy.assert_called_once()
    assert guard._strip is None
    assert not guard._session().active


def test_back_to_lock_when_not_studying_is_harmless(tmp_path: Path, hmac_key: Path):
    guard = locked_guard(tmp_path, hmac_key)

    guard._back_to_lock()

    guard._lock.root.grab_set_global.assert_not_called()


def test_a_failed_regrab_is_reported_on_the_surface(
    tmp_path: Path, hmac_key: Path, no_spawn
):
    """A degraded lock must say so rather than look identical to a working
    one."""
    guard = locked_guard(tmp_path, hmac_key, demo_mode=False)
    guard._open_problem(URL)
    guard._lock.root.grab_set_global.side_effect = tk.TclError("taken")
    for view in guard._views.values():
        view.status_line.configure.reset_mock()

    guard._back_to_lock()

    for view in guard._views.values():
        view.status_line.configure.assert_called()
