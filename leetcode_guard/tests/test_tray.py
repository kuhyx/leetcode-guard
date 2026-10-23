"""Tests for the tray script's click: open the status app, or say why not.

``scripts/leetcode_guard_tray.py`` is not a package module (it is installed
into ``~/.config/i3/scripts``), so it is loaded from its path, with GTK
replaced by mocks: CI has no PyGObject and no display.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

TRAY_PATH = Path(__file__).resolve().parents[2] / "scripts" / "leetcode_guard_tray.py"


@pytest.fixture
def tray(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    gi = MagicMock()
    monkeypatch.setitem(sys.modules, "gi", gi)
    monkeypatch.setitem(sys.modules, "gi.repository", gi.repository)
    spec = importlib.util.spec_from_file_location("leetcode_guard_tray", TRAY_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "APP_LAUNCHER", tmp_path / "leetcode_guard_app.sh")
    return module


class Recorder:
    """Stands in for ``subprocess.Popen`` and ``subprocess.run`` at once."""

    def __init__(self, summary: str = "LOCKED - solve 1 problem") -> None:
        self.started: list[list[str]] = []
        self.ran: list[list[str]] = []
        self.summary = summary

    def popen(self, command: list[str], **kwargs: object) -> object:
        assert kwargs.get("start_new_session") is True
        self.started.append(command)
        return SimpleNamespace(pid=1)

    def run(self, command: list[str], **_kwargs: object) -> object:
        self.ran.append(command)
        return SimpleNamespace(stdout=f"{self.summary}\n", returncode=0)


def _wire(monkeypatch: pytest.MonkeyPatch, tray: ModuleType) -> Recorder:
    recorder = Recorder()
    monkeypatch.setattr(tray.subprocess, "Popen", recorder.popen)
    monkeypatch.setattr(tray.subprocess, "run", recorder.run)
    return recorder


def test_the_launcher_is_the_status_apps(tray: Any):
    assert TRAY_PATH.is_file()
    assert tray.APP_LAUNCHER.name == "leetcode_guard_app.sh"
    assert tray.DEFAULT_APP_LAUNCHER.parts[-3:] == (
        "app",
        "tool",
        "leetcode_guard_app.sh",
    )


def test_the_status_cli_is_the_new_module(tray: Any):
    assert tray.STATUS_CMD[-2:] == ["-m", "leetcode_guard.status_cli"]


def test_a_click_launches_the_app(monkeypatch: pytest.MonkeyPatch, tray: Any):
    tray.APP_LAUNCHER.write_text("#!/bin/bash\n", encoding="utf-8")
    recorder = _wire(monkeypatch, tray)

    tray.open_app(MagicMock())

    assert recorder.started == [["/bin/bash", str(tray.APP_LAUNCHER)]]
    assert recorder.ran == []


def test_a_missing_launcher_warns_and_notifies_the_summary(
    monkeypatch: pytest.MonkeyPatch, tray: Any, caplog: pytest.LogCaptureFixture
):
    recorder = _wire(monkeypatch, tray)

    tray.open_app(MagicMock())

    assert recorder.started == []
    assert "launcher" in caplog.text
    assert str(tray.APP_LAUNCHER) in caplog.text
    assert recorder.ran[0][-1] == "--summary"
    notify = recorder.ran[1]
    assert notify[0] == tray.NOTIFY_SEND
    assert notify[-1] == "LOCKED - solve 1 problem"


def test_a_launcher_that_will_not_start_falls_back_too(
    monkeypatch: pytest.MonkeyPatch, tray: Any, caplog: pytest.LogCaptureFixture
):
    tray.APP_LAUNCHER.write_text("#!/bin/bash\n", encoding="utf-8")
    recorder = _wire(monkeypatch, tray)

    def refuse(_command: list[str], **_kwargs: object) -> object:
        message = "no bash"
        raise OSError(message)

    monkeypatch.setattr(tray.subprocess, "Popen", refuse)

    tray.open_app(MagicMock())

    assert "could not start" in caplog.text
    assert recorder.ran[1][0] == tray.NOTIFY_SEND


def test_an_unavailable_summary_still_notifies(
    monkeypatch: pytest.MonkeyPatch, tray: Any
):
    recorder = _wire(monkeypatch, tray)
    recorder.summary = ""

    tray.open_app(MagicMock())

    assert recorder.ran[1][-1] == "leetcode-guard: status unavailable"


def test_a_failed_notification_is_a_warning(
    monkeypatch: pytest.MonkeyPatch, tray: Any, caplog: pytest.LogCaptureFixture
):
    def run(command: list[str], **_kwargs: object) -> object:
        if command[0].endswith("notify-send"):
            raise subprocess.TimeoutExpired(command, 5)
        return SimpleNamespace(stdout="ok\n", returncode=0)

    monkeypatch.setattr(tray.subprocess, "run", run)

    tray.open_app(MagicMock())

    assert "could not show" in caplog.text
