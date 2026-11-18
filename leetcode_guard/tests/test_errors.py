# Copyright (c) 2026 Krzysztof Rudnicki
"""leetcode-guard's error reporting: installed once, into the shared spool."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from leetcode_guard import _errors, _lock
from leetcode_guard.tests._guard_factories import create_guard

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_install_keeps_the_reporter_and_writes_the_spool(tmp_path: Path) -> None:
    """The CLI's install names this app and its repo in every report."""
    rep = _errors.install()
    assert _errors.SLOT.reporter is rep
    assert rep.app == "leetcode-guard"
    rep.report("uncaught.python", ValueError("deliberate"))
    line = (tmp_path / "app-errors-spool" / "leetcode-guard.jsonl").read_text()
    entry = json.loads(line)
    assert entry["repo"] == "kuhyx/leetcode-guard"
    assert entry["error"] == "ValueError: deliberate"


def test_lock_window_watches_stalls_once_installed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A lock window built after install reports its own freezes."""
    watch = MagicMock()
    monkeypatch.setattr(_lock, "watch_stalls", watch)
    monkeypatch.setattr(_errors.SLOT, "reporter", MagicMock())
    guard, _ = create_guard(tmp_path)
    guard.run()
    watch.assert_called_once_with(guard.root, _errors.SLOT.reporter)


def test_stall_clock_starts_with_the_event_loop_not_the_constructor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Construction blocks the Tk thread before mainloop, by design.

    gatelock's ``wait_for_turn`` sleeps a 1.5 s startup grace and the surfaces
    are built synchronously, all before the event loop runs. A watch armed at
    ``GateRoot()`` counted that as a frozen loop: every lock filed a ~1.6 s
    ``slow wait: tk.mainloop`` (c890f31a, 2026-11-18). The watch starts when
    ``run`` hands control to Tk.
    """
    watch = MagicMock()
    monkeypatch.setattr(_lock, "watch_stalls", watch)
    monkeypatch.setattr(_errors.SLOT, "reporter", MagicMock())
    guard, _ = create_guard(tmp_path)
    watch.assert_not_called()
    guard.run()
    watch.assert_called_once()


def test_no_reporter_means_no_stall_watch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tests and tools that never installed the reporter watch nothing."""
    watch = MagicMock()
    monkeypatch.setattr(_lock, "watch_stalls", watch)
    monkeypatch.setattr(_errors.SLOT, "reporter", None)
    guard, _ = create_guard(tmp_path)
    guard.run()
    watch.assert_not_called()
