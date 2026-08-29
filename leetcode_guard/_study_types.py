"""The values a study-mode transition is described in.

Split out of ``_study.py`` for the 250-line cap. They live apart from both
halves of the transition because both halves construct them, and a module that
only holds values can be imported by anything without a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
import enum
from typing import Any


class StudyState(enum.Enum):
    """Whether the lock is currently asserted."""

    LOCKED = "locked"
    STUDYING = "studying"


@dataclass(frozen=True)
class SuspendOutcome:
    """What one transition managed to do.

    ``steps`` is an audit trail rather than decoration: a transition that got
    halfway is a real state, and naming the steps that completed makes it an
    inspectable value instead of something inferred from a log afterwards.
    """

    ok: bool
    reason: str
    steps: tuple[str, ...] = ()


@dataclass
class Withdrawn:
    """A surface hidden by ``StudySession.suspend``."""

    name: str
    window: Any
    rect: Any
