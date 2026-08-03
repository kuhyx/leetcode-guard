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

from dataclasses import dataclass
import logging
import tkinter as tk
from typing import TYPE_CHECKING, Any, Final

from gatelock import EscapeDraft, EscapePolicy, EscapeTracker

from leetcode_guard._constants import (
    HISTORY_REVIEW_COUNT,
    JUSTIFICATION_MIN_CHARS,
    UNVERIFIABLE_HATCH_SECONDS,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

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

ESCAPE_OFFER_AFTER_SECONDS: Final = 600
"""Ten minutes of an ordinary lock before the hatch is even visible.

Overridden entirely when the network is the problem: see
:func:`is_offerable`, which reveals it after
:data:`~leetcode_guard._constants.UNVERIFIABLE_HATCH_SECONDS` of consecutive
failed checks. Making someone wait out a full offer delay while the gate
cannot see LeetCode at all would be punishing them for an outage.
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


@dataclass
class EscapeForm:
    """The widgets of an open escape form."""

    frame: Any
    reason: Any
    onset: Any
    """When the problem started.

    Not decorative: ``EscapeTracker.validate`` rejects a blank onset outright,
    so a form without this field can never be submitted at all. That is exactly
    how it shipped in the first draft -- the hatch was present, clickable, and
    permanently refused.
    """

    description: Any
    complaint: Any
    submit: Any


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
        config = self._config
        frame = tk.Frame(parent, bg=config.field_bg)
        frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            frame,
            text=(
                f"{self._tracker.budget_summary()}\n"
                f"Explain, in at least {JUSTIFICATION_MIN_CHARS} characters, why "
                "you cannot solve a problem today."
            ),
            font=config.font("label"),
            fg=config.fg,
            bg=config.field_bg,
            justify="left",
        ).pack(padx=config.space("md"), pady=(config.space("md"), config.space("sm")))

        tk.Label(
            frame,
            text="What is the problem, in a few words?",
            font=config.font("caption"),
            fg=config.muted,
            bg=config.field_bg,
        ).pack(padx=config.space("md"), pady=(config.space("xs"), 0))
        reason = tk.Entry(frame, width=60, bg=config.bg, fg=config.fg)
        reason.pack(padx=config.space("md"), pady=config.space("xs"))

        tk.Label(
            frame,
            text="When did this start?",
            font=config.font("caption"),
            fg=config.muted,
            bg=config.field_bg,
        ).pack(padx=config.space("md"), pady=(config.space("xs"), 0))
        onset = tk.Entry(frame, width=60, bg=config.bg, fg=config.fg)
        onset.pack(padx=config.space("md"), pady=config.space("xs"))

        tk.Label(
            frame,
            text=(
                f"The full explanation (at least {JUSTIFICATION_MIN_CHARS} characters):"
            ),
            font=config.font("caption"),
            fg=config.muted,
            bg=config.field_bg,
        ).pack(padx=config.space("md"), pady=(config.space("xs"), 0))
        description = tk.Text(frame, width=60, height=6, bg=config.bg, fg=config.fg)
        description.pack(padx=config.space("md"), pady=config.space("xs"))

        recent = self._tracker.format_recent()
        if recent:
            tk.Label(
                frame,
                text=recent,
                font=config.font("caption"),
                fg=config.muted,
                bg=config.field_bg,
                justify="left",
                wraplength=700,
            ).pack(padx=config.space("md"), pady=config.space("xs"))

        complaint = tk.Label(
            frame,
            text="",
            font=config.font("caption"),
            fg=config.danger,
            bg=config.field_bg,
        )
        complaint.pack(padx=config.space("md"), pady=config.space("xs"))

        submit = tk.Button(
            frame,
            text="Submit",
            fg=config.on_fill,
            bg=config.warning,
            command=self.submit,
            relief="flat",
        )
        submit.pack(
            padx=config.space("md"), pady=(config.space("xs"), config.space("md"))
        )

        self._form = EscapeForm(
            frame=frame,
            reason=reason,
            onset=onset,
            description=description,
            complaint=complaint,
            submit=submit,
        )
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
