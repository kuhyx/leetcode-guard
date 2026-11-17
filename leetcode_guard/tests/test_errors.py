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
    watch.assert_called_once_with(guard.root, _errors.SLOT.reporter)
