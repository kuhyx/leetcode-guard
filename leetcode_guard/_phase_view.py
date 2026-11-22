"""What the lock shows about the current unit (display side of the theory-first flow)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Phase = Literal["theory", "solve", "none"]


@dataclass(frozen=True)
class PhaseView:
    """The current unit and what the lock leads with."""

    unit: str
    phase: Phase
    cards_taught: int | None
    cards_total: int | None
    lessons_ready: bool
    minutes_per_credit: int
    theory_minutes_today: int
    solved: int
    total: int
    learn_target: tuple[str, str] | None
