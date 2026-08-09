"""Tests for the study-mode wiring: Open, the strip, and the ways back.

The ordering that matters here is "browser first, grab second" -- discovering
there is no browser *after* standing the lock down would leave the machine
unguarded for nothing.
"""

from __future__ import annotations

import logging
import tkinter as tk
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from leetcode_guard.tests._guard_factories import UNVERIFIABLE, create_guard, probe_of

if TYPE_CHECKING:
    from pathlib import Path

URL = "https://leetcode.com/problems/two-sum/"


@pytest.fixture
def no_spawn(monkeypatch):
    """A browser that always resolves and never actually runs."""
    launched: list[str] = []
    monkeypatch.setattr(
        "leetcode_guard._lock_study.find_opener", lambda: "/usr/bin/xdg-open"
    )

    def fake_launch(url: str):
        launched.append(url)
        return MagicMock(ok=True, reason="opened", command=())

    monkeypatch.setattr("leetcode_guard._lock_study.launch", fake_launch)
    return launched


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


# -- opening ---------------------------------------------------------------


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


# -- leaving ---------------------------------------------------------------


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


def test_a_real_solve_while_studying_puts_the_lock_back_first(
    tmp_path: Path, hmac_key: Path, no_spawn
):
    """The primary exit. The unlocked screen has to land on a surface that is
    actually mapped, or the good news flashes onto a hidden window."""
    guard, _ = create_guard(
        tmp_path,
        probe=probe_of("old-1"),
        poll_probe=probe_of("brand-new", "also-new", "old-1"),
        key_file=hmac_key,
        seeded=True,
        demo_mode=False,
    )
    guard._lock._recovery = MagicMock()
    guard._lock._detector = MagicMock()
    guard._open_problem(URL)
    strip = guard._strip
    assert guard._session().active

    guard._on_poll_result(guard._check())

    assert not guard._session().active
    strip.window.destroy.assert_called_once()
    guard._lock.root.grab_set_global.assert_called()
    assert not guard._decision().locked


def test_closing_during_study_restores_vt_bookkeeping(
    tmp_path: Path, hmac_key: Path, no_spawn
):
    """Suspend cleared gatelock's ``_vt_disabled`` to match reality. If close
    ran without resuming, gatelock would skip its own restore and the machine
    would exit with VT switching still disabled."""
    guard = locked_guard(tmp_path, hmac_key, demo_mode=False)
    guard._open_problem(URL)
    assert guard._lock._vt_disabled is False

    guard.on_close()

    assert not guard._session().active


def test_an_unverifiable_poll_during_study_leaves_it_running(
    tmp_path: Path, hmac_key: Path, no_spawn
):
    """A blind check is not a reason to yank the browser away mid-problem."""
    guard = locked_guard(tmp_path, hmac_key, poll_probe=UNVERIFIABLE)
    guard._open_problem(URL)

    guard._on_poll_result(UNVERIFIABLE)

    assert guard._session().active


# -- the strip's contents --------------------------------------------------


def test_the_strip_text_reports_what_is_still_owed(
    tmp_path: Path, hmac_key: Path, no_spawn
):
    guard = locked_guard(tmp_path, hmac_key)

    text = guard._strip_text()

    assert text.needed >= 1
    assert "Still need" in text.owed
    assert "Studying for" in text.elapsed


def test_the_strip_falls_back_to_the_first_output_when_none_is_primary(
    tmp_path: Path, hmac_key: Path, no_spawn
):
    """A desk with no output flagged primary still gets a strip somewhere
    visible rather than none at all."""
    guard = locked_guard(tmp_path, hmac_key)
    only = guard._lock.surfaces.infos()[0]
    plain = SimpleNamespace(
        output_name=only.output_name, rect=only.rect, index=0, is_primary=False
    )
    guard._lock._surfaces = MagicMock()
    guard._lock._surfaces.infos.return_value = (plain,)

    assert guard._primary_rect() is plain.rect


def test_dropping_a_strip_that_was_never_built_is_harmless(
    tmp_path: Path, hmac_key: Path
):
    guard = locked_guard(tmp_path, hmac_key)

    guard._drop_strip()

    assert guard._strip is None


def test_a_launcher_that_raises_never_strands_the_machine_unlocked(
    tmp_path: Path, hmac_key: Path, monkeypatch, caplog
):
    """The grab is already released by the time the browser is spawned, so
    anything escaping there skips the rollback and walks away from an open
    machine. `launch` promises not to raise; this asserts the caller does not
    depend on that promise being kept."""
    monkeypatch.setattr(
        "leetcode_guard._lock_study.find_opener", lambda: "/usr/bin/xdg-open"
    )

    def exploding_launch(_url):
        message = "embedded null byte"
        raise ValueError(message)

    monkeypatch.setattr("leetcode_guard._lock_study.launch", exploding_launch)
    guard = locked_guard(tmp_path, hmac_key, demo_mode=False)

    with caplog.at_level(logging.ERROR):
        guard._open_problem(URL)

    assert not guard._session().active, "study mode must not stay active"
    guard._lock.root.grab_set_global.assert_called()
    assert caplog.records
