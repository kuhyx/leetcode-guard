"""View-model and mock-surface builders shared by the ``test_view*`` modules."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from gatelock import LockConfig

from leetcode_guard._constants import PROBLEM_DISPLAY_LIMIT
from leetcode_guard._view import GuardView
from leetcode_guard._view_types import ProblemList, ViewHooks
from leetcode_guard._viewmodel import ViewModel
from leetcode_guard._viewmodel_lines import ProblemLine

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


def rows_view(count: int, *, rows: int = PROBLEM_DISPLAY_LIMIT):
    """A surface with ``count`` built rows, each row frame its own mock."""
    labels = [MagicMock(name=f"label{i}") for i in range(count)]
    for label in labels:
        label.master = MagicMock(name="row")
    return mock_view(
        problems=ProblemList(
            labels=labels,
            buttons=[MagicMock(name=f"open{i}") for i in range(count)],
            marks=[MagicMock(name=f"mark{i}") for i in range(count)],
            scroll=MagicMock(),
            shown=count,
            fitted=(rows, min(count, rows)),
        ),
        hooks=ViewHooks(on_open=lambda _u: None),
    )
