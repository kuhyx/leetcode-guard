"""Why the gate reached its verdict (split out of ``_gate`` for file length)."""

from __future__ import annotations

import enum


class GateState(enum.Enum):
    """Why the gate reached its verdict."""

    UNLOCKED_NOT_STARTED = "not-started"
    """Today is before :data:`GATE_START_DATE`. The gate is installed but not
    yet in force."""

    UNLOCKED_ALREADY_CHARGED = "already-charged"
    """Today was settled by an earlier run. Re-running is a no-op, which is
    what makes the afternoon retry safe."""

    UNLOCKED_CHARGED_NOW = "charged"
    """Enough credit was available; this run spent it."""

    LOCKED_INSUFFICIENT = "locked"
    """Not enough credit. Solve something."""

    LOCKED_CLOCK_UNTRUSTED = "locked-clock"
    """The system date moved backwards past a settled day."""

    UNLOCKED_FREE_DAY = "free-day"
    """Today is in the shared free-day pool. No lock, and no charge either --
    a day off is not paid for out of the credit balance."""

    UNLOCKED_SICK_DAY = "sick-day"
    """Today is in the shared *sick*-day pool (not the free-day pool): no lock,
    no charge, nothing added to the debt."""

    UNLOCKED_FOCUS_DAY = "focus-day"
    """An active focus project replaces this gate today: no lock, no charge,
    nothing added to the debt, and today costs nothing."""
