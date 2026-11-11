"""A study session whose resume cannot re-take the input grab."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import tkinter as tk
from typing import TYPE_CHECKING, Any

from leetcode_guard.tests._study_fixtures import session, wired

if TYPE_CHECKING:
    import pytest

    from leetcode_guard._study import StudySession, SuspendOutcome


@dataclass
class FailedRegrab:
    """What a resume that lost the grab left behind."""

    lock: Any
    study: StudySession
    outcome: SuspendOutcome
    told: list[str] = field(default_factory=list)


def resume_without_grab(
    caplog: pytest.LogCaptureFixture, holder: str, *outputs: str
) -> FailedRegrab:
    """Suspend, then resume while *holder* keeps the global grab.

    Args:
        caplog: pytest's log capture, set to ERROR around the resume.
        holder: The ``TclError`` text every grab attempt raises.
        *outputs: The outputs the lock spans (``DP-0`` if none).

    Returns:
        The lock, the session, its outcome and every fail-closed report.
    """
    _parent, lock = wired(*outputs)
    lock.root.grab_set_global.side_effect = tk.TclError(holder)
    told: list[str] = []
    study = session(lock, on_fail=told.append)
    study.suspend()

    with caplog.at_level(logging.ERROR):
        outcome = study.resume()

    return FailedRegrab(lock=lock, study=study, outcome=outcome, told=told)
