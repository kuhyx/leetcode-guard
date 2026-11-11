"""View-model and mock-surface builders shared by the ``test_view*`` modules."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from gatelock import LockConfig

from leetcode_guard._view import GuardView
from leetcode_guard._viewmodel import ProblemLine, ViewModel

CONFIG = LockConfig()


def model(**kwargs) -> ViewModel:
    """A locked view model with one problem and one note; kwargs override fields."""
    base = {
        "headline": "Solve 1 LeetCode problem to unlock",
        "balance_line": "Credits 0  |  Monday costs 1",
        "status_line": "Watching...",
        "notes": ("a note",),
        "problems": (ProblemLine(label="1. Two Sum", url="https://x/"),),
        "unlocked": False,
        "show_escape": False,
    }
    base.update(kwargs)
    return ViewModel(**base)


def mock_view(**extra: Any) -> GuardView:
    """A ``DP-0`` surface whose core widgets are mocks; ``extra`` sets the rest."""
    return GuardView(
        output_name="DP-0",
        container=MagicMock(),
        headline=MagicMock(),
        balance_line=MagicMock(),
        status_line=MagicMock(),
        notes_label=MagicMock(),
        **extra,
    )
