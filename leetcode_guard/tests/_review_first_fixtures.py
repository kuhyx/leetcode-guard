"""Shared by the review-first tests: the SOLVE phase with a module to review."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from leetcode_guard._review_due import DueRead, DueStatus
from leetcode_guard.tests._ledger_fixtures import NOW
from leetcode_guard.tests._phase_fixtures import SOLVE, SUBJECT, unit_pool
from leetcode_guard.tests._tutor_fixtures import due_row, write_due
from leetcode_guard.tests.test_lock_study import locked_guard

if TYPE_CHECKING:
    from pathlib import Path

TARGET = (SUBJECT, "prefix-sums")
ROUTE = f"/review/{SUBJECT}/prefix-sums"
DUE = DueRead(DueStatus.DUE, 3, TARGET)
SOLVE_R = replace(SOLVE, review_targets=(TARGET,))
T_MS = int(NOW.timestamp() * 1000)


def write_module_due(key: Path, due_ms: list[int]) -> None:
    """``review_due.json`` with one signed row for the unit's module."""
    write_due([due_row("prefix-sums", due_ms, at=10.0, key_file=key)])


def slugs_of(model) -> list[str]:
    """The slugs on a view model's rows."""
    return [line.slug for line in model.problems]


def install_tutor(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """A tutor launcher that resolves and records; the browser must not run."""
    launched: list[str] = []
    monkeypatch.setattr("leetcode_guard._lock_learn.find_tutor", lambda: "/x/tutor")
    monkeypatch.setattr("leetcode_guard._lock_phase.find_tutor", lambda: "/x/tutor")

    def launch_tutor(route: str) -> MagicMock:
        launched.append(route)
        return MagicMock(ok=True, reason="opened")

    monkeypatch.setattr("leetcode_guard._lock_learn.launch_tutor", launch_tutor)
    monkeypatch.setattr("leetcode_guard._lock_study.find_opener", lambda: "/x/open")
    monkeypatch.setattr(
        "leetcode_guard._lock_study.launch",
        lambda url: pytest.fail(f"the browser was asked to open {url}"),
    )
    return launched


def review_guard(tmp_path: Path, key: Path, **kwargs):
    """A lock on a SOLVE unit with a module to review.

    Not the demo by default: the demo never reads the tutor's file.
    """
    kwargs.setdefault("demo_mode", False)
    return locked_guard(
        tmp_path, key, pool=unit_pool(), phase=lambda: SOLVE_R, **kwargs
    )
