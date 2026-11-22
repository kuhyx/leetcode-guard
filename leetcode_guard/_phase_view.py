"""What the lock shows about the current unit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Phase = Literal["theory", "solve", "none"]


# One record per repaint, flat on purpose: it is the C5 contract the status
# surfaces serialise field by field, so nesting it would change their shape.
@dataclass(frozen=True)
class PhaseView:  # pylint: disable=too-many-instance-attributes
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
    rework_target: tuple[str, str] | None = None
    """SOLVE only: (subject, the unit's first module), where rework cards go."""
