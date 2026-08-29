"""The sanctioned way out when solving genuinely is not happening.

A hard lock whose unlock condition depends on a third-party website needs a
bounded escape, or a LeetCode outage is a bricked machine. Built on the shared
``gatelock._escape`` core rather than a private copy, so it is exactly as hard
as screen-locker's sick mode and wake-alarm's can't-wake hatch:

* the button only appears after the lock has been up a while, so it is never
  the easy first move;
* it disappears entirely once a rolling budget is spent;
* it costs a written justification, with the last ten shown back;
* it costs a wait that doubles with each recent use;
* every entry is HMAC-signed, so editing the history is detectable.

Using it still writes a full-cost charge for the day, so the balance goes
negative and the debt carries. An escaped day is forgiven, not free.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from gatelock import EscapeDraft, EscapePolicy, EscapeTracker

from leetcode_guard._constants import (
    HISTORY_REVIEW_COUNT,
    JUSTIFICATION_MIN_CHARS,
    UNVERIFIABLE_HATCH_SECONDS,
)
from leetcode_guard._escape_form import EscapeForm, build_escape_form

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    import tkinter as tk

    from gatelock import LockConfig

_logger: Final = logging.getLogger(__name__)

GUARD_ESCAPE_POLICY: Final = EscapePolicy(
    name="cannot-grind",
    label="Cannot-grind",
    justification_min_chars=JUSTIFICATION_MIN_CHARS,
    history_review_count=HISTORY_REVIEW_COUNT,
)
"""Budgets left at the shared defaults, so this is exactly as hard to abuse as
the sibling lockers' hatches."""

ESCAPE_OFFER_AFTER_SECONDS: Final = 0
"""No delay: the hatch is on screen from the first second.

This was ten minutes, on the theory that a hatch you have to wait for is one
you will not reach for lightly. What that actually bought was a lock with no
exit at all for its first ten minutes. On 2026-08-05 the gate armed demanding a
solve the user could not perform, and the hatch -- the one control that would
have ended it -- was still four minutes away at the point the services had to
be killed from an already-open terminal. A safety valve that opens ten minutes
into the fire is not a safety valve.

What makes the hatch hard to abuse is the **budget**, not the clock: one use
per 7 days, three per 30, ten per 90, plus 120 characters of written
justification and a read-back of the last ten. Those are intact, and they are
the parts that survive contact with a user who is genuinely stuck. The
comparison below is kept rather than deleted so restoring a delay stays a
one-line change.
"""


def build_tracker(path: Path, *, key_file: Path | None = None) -> EscapeTracker:
    """Build the tracker over its own history file."""
    tracker = EscapeTracker(GUARD_ESCAPE_POLICY, path, key_file=key_file)
    tracker.load()
    return tracker


def is_offerable(
    tracker: EscapeTracker,
    *,
    elapsed_seconds: float,
    unverifiable_seconds: float,
) -> bool:
    """Whether to show the hatch at all.

    Two ways in, one veto. Either the lock has simply been up a long time, or
    the gate has been unable to reach LeetCode for a sustained stretch -- the
    second path is much shorter, because that is the case where the user cannot
    possibly satisfy the condition. The veto is the budget: once spent, the
    hatch is gone entirely, not greyed out.
    """
    if tracker.is_budget_exhausted():
        return False
    if unverifiable_seconds >= UNVERIFIABLE_HATCH_SECONDS:
        return True
    return elapsed_seconds >= ESCAPE_OFFER_AFTER_SECONDS


class EscapeHatch:
    """Owns the escape form's lifecycle on one surface."""

    def __init__(
        self,
        tracker: EscapeTracker,
        config: LockConfig,
        *,
        on_granted: Callable[[str], None],
    ) -> None:
        """Create the hatch.

        Args:
            tracker: The budget and history store.
            config: Design tokens.
            on_granted: Called with the recorded justification once the form is
                accepted.
        """
        self._tracker = tracker
        self._config = config
        self._on_granted = on_granted
        self._form: EscapeForm | None = None

    @property
    def open(self) -> bool:
        """Whether a form is currently showing."""
        return self._form is not None

    def show(self, parent: tk.Misc) -> EscapeForm:
        """Build the form over ``parent``."""
        self._form = build_escape_form(parent, self._config, self._tracker, self.submit)
        return self._form

    def submit(self) -> bool:
        """Validate and, if acceptable, record the escape.

        Returns:
            Whether the escape was granted.
        """
        form = self._form
        if form is None:
            return False
        draft = EscapeDraft(
            reason=form.reason.get().strip(),
            onset=form.onset.get().strip(),
            severity=1,
            description=form.description.get("1.0", "end").strip(),
        )
        complaint = self._tracker.validate(draft)
        if complaint is not None:
            form.complaint.configure(text=complaint)
            return False
        if not self._tracker.record(draft):
            form.complaint.configure(text="Could not record the escape -- try again.")
            _logger.error("failed to record an escape-hatch use")
            return False
        _logger.warning("escape hatch used: %s", draft.reason)
        self.close()
        self._on_granted(draft.reason)
        return True

    def close(self) -> None:
        """Tear the form down."""
        if self._form is None:
            return
        self._form.frame.destroy()
        self._form = None
