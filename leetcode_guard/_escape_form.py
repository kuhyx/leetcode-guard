"""Build the escape form's widgets.

Split out of ``_escape_flow.py`` for the 250-line cap: that module owns the
hatch's lifecycle and the validation, this one is pure painting.

``onset`` is not decorative. ``EscapeTracker.validate`` rejects a blank one
outright, so a form without that field can never be submitted at all -- which
is how the hatch shipped in its first draft: present, clickable, and
permanently refused.
"""

from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from typing import TYPE_CHECKING, Any

from leetcode_guard._constants import JUSTIFICATION_MIN_CHARS

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import LockConfig

    from leetcode_guard._escape import EscapeTracker


@dataclass
class EscapeForm:
    """The widgets of an open escape form."""

    frame: Any
    reason: Any
    onset: Any
    description: Any
    complaint: Any
    submit: Any


def build_escape_form(
    parent: tk.Misc,
    config: LockConfig,
    tracker: EscapeTracker,
    on_submit: Callable[[], bool],
) -> EscapeForm:
    """Build the form over ``parent`` and return its widgets."""
    frame = tk.Frame(parent, bg=config.field_bg)
    frame.place(relx=0.5, rely=0.5, anchor="center")

    tk.Label(
        frame,
        text=(
            f"{tracker.budget_summary()}\n"
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
        text=(f"The full explanation (at least {JUSTIFICATION_MIN_CHARS} characters):"),
        font=config.font("caption"),
        fg=config.muted,
        bg=config.field_bg,
    ).pack(padx=config.space("md"), pady=(config.space("xs"), 0))
    description = tk.Text(frame, width=60, height=6, bg=config.bg, fg=config.fg)
    description.pack(padx=config.space("md"), pady=config.space("xs"))

    recent = tracker.format_recent()
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
        command=on_submit,
        relief="flat",
    )
    submit.pack(padx=config.space("md"), pady=(config.space("xs"), config.space("md")))

    return EscapeForm(
        frame=frame,
        reason=reason,
        onset=onset,
        description=description,
        complaint=complaint,
        submit=submit,
    )
