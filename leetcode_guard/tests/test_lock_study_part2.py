"""Continued from :mod:`leetcode_guard.tests.test_lock_study`, split for the 250-line cap."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from leetcode_guard.tests._guard_factories import UNVERIFIABLE, create_guard, probe_of

if TYPE_CHECKING:
    from pathlib import Path

from leetcode_guard.tests.test_lock_study import (
    URL,
    locked_guard,
)


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
