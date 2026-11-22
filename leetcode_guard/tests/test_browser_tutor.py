"""Resolving and spawning the tutor launcher (SPEC C4), never for real."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from leetcode_guard import _browser
from leetcode_guard._browser import find_tutor, launch_tutor

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

ROUTE = "/learn/leetcode-easy-algorithms-in-typescript/prefix-sums"


class _Spawn:
    def __init__(self, *, fail: Exception | None = None) -> None:
        self.calls: list[tuple[tuple[str, ...], bool]] = []
        self.fail = fail
        self.last: object = None

    def __call__(self, args, *, start_new_session):
        if self.fail is not None:
            raise self.fail
        self.calls.append((tuple(args), start_new_session))
        self.last = object()
        return self.last


def _home(
    monkeypatch: pytest.MonkeyPatch,
    home: Path,
    *,
    on_path: str | None,
    runner: str | None = None,
) -> None:
    """Scratch HOME; ``which`` knows ``tutor`` and ``systemd-run`` only."""
    table = {"tutor": on_path, "systemd-run": runner}
    monkeypatch.setattr(_browser.Path, "home", lambda: home)
    monkeypatch.setattr("leetcode_guard._browser.shutil.which", table.get)


def _install(home: Path, *, mode: int = 0o755) -> Path:
    launcher = home / ".local" / "bin" / "tutor"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(mode)
    return launcher


def test_path_wins_so_a_fake_launcher_can_stand_in(monkeypatch, tmp_path: Path):
    """``tutor`` on PATH first: the grab check puts a fake there."""
    _install(tmp_path)
    _home(monkeypatch, tmp_path, on_path="/fake/bin/tutor")

    assert find_tutor() == "/fake/bin/tutor"


def test_the_user_bin_is_found_when_path_lacks_it(monkeypatch, tmp_path: Path):
    """The systemd user PATH has no ``~/.local/bin``; the fallback covers it."""
    launcher = _install(tmp_path)
    _home(monkeypatch, tmp_path, on_path=None)

    assert find_tutor() == str(launcher)


def test_a_missing_or_non_executable_launcher_is_none(monkeypatch, tmp_path: Path):
    """Nothing to run means no suspend: ``None``, without spawning anything."""
    _home(monkeypatch, tmp_path, on_path=None)
    assert find_tutor() is None

    _install(tmp_path, mode=0o644)
    assert find_tutor() is None


def test_launch_without_systemd_run_runs_the_bare_command(monkeypatch, tmp_path: Path):
    """No ``systemd-run`` on PATH: the tutor runs bare, as the browser does."""
    _home(monkeypatch, tmp_path, on_path="/fake/bin/tutor")
    spawn = _Spawn()

    result = launch_tutor(ROUTE, spawn=spawn)

    assert result.ok
    assert result.process is spawn.last  # the handle the lock watches the exit on
    assert spawn.calls == [(("/fake/bin/tutor", "--route", ROUTE), True)]


def test_launch_gets_its_own_scope_outside_the_lock_cgroup(monkeypatch, tmp_path: Path):
    """The tutor's ``setsid -f`` stays in the caller's cgroup, so a window
    cold-started from the lock died with ``leetcode-guard.service``: mid-lesson,
    the moment the lock cleared. A transient scope is its own cgroup."""
    _home(
        monkeypatch, tmp_path, on_path="/fake/bin/tutor", runner="/usr/bin/systemd-run"
    )
    spawn = _Spawn()

    result = launch_tutor(ROUTE, spawn=spawn)

    flags = ["--user", "--scope", "--collect", "--quiet"]
    expected = ("/usr/bin/systemd-run", *flags, "/fake/bin/tutor", "--route", ROUTE)
    assert spawn.calls == [(expected, True)]
    assert result.command == expected
    assert "/fake/bin/tutor" in result.reason


def test_no_launcher_is_reported_not_raised(monkeypatch, tmp_path: Path, caplog):
    """Missing: a failed result and a warning, never an exception."""
    _home(monkeypatch, tmp_path, on_path=None)

    with caplog.at_level(logging.WARNING):
        result = launch_tutor(ROUTE, spawn=_Spawn())

    assert not result.ok
    assert "tutor" in caplog.text


def test_a_spawn_failure_is_a_failed_result(monkeypatch, tmp_path: Path):
    """An unlinked launcher or a NUL in the route: failed, not raised."""
    _home(monkeypatch, tmp_path, on_path="/fake/bin/tutor")

    for error in (OSError("gone"), ValueError("embedded null byte")):
        result = launch_tutor(ROUTE, spawn=_Spawn(fail=error))
        assert not result.ok
        assert result.command == ("/fake/bin/tutor", "--route", ROUTE)
