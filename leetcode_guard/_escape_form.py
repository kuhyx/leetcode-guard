"""Build the escape form's widgets.

Split out of ``_escape_flow.py`` for the 250-line cap: that module owns the
hatch's lifecycle and the validation, this one is pure painting.

``onset`` is not decorative. ``EscapeTracker.validate`` rejects a blank one
outright, so a form without that field can never be submitted at all -- which
is how the hatch shipped in its first draft: present, clickable, and
permanently refused.

**No words** (textgate): each field is marked by a glyph, the budget is drawn
as filled/hollow dots per rolling window, the length rule is a live
``written/required`` counter that turns green, and a refusal outlines the
field it is about in red. gatelock's own sentences (``budget_summary``,
``validate``'s complaint, ``format_recent``) are never painted; the past
justifications are -- they are what the user typed.
"""

from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from typing import TYPE_CHECKING, Any

from leetcode_guard import _glyphs as g

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import EscapeDraft, EscapeTracker, LockConfig

_WINDOWS = (7, 30, 90)
_HIGHLIGHT_PX = 2


@dataclass
class EscapeForm:
    """The widgets of an open escape form."""

    frame: Any
    reason: Any
    onset: Any
    description: Any
    complaint: Any
    submit: Any
    counter: Any = None
    """``written/required`` under the explanation box."""
    flagged: Any = None
    """The field the last refusal outlined, if any."""


def budget_marks(tracker: EscapeTracker) -> str:
    """``⎋  ●○  │  ●○○  │  ●●○○○○○○○○``: uses per week, month, quarter."""
    policy = tracker.policy
    caps = (
        policy.budget_per_7_days,
        policy.budget_per_30_days,
        policy.budget_per_90_days,
    )
    groups = []
    for days, cap in zip(_WINDOWS, caps, strict=True):
        used = min(tracker.count_in_window(days), cap)
        if cap > g.DOT_CAP:
            groups.append(f"{used}/{cap}")
        else:
            groups.append("●" * used + "○" * (cap - used))
    return f"{g.ESCAPE}  " + g.SEP.join(groups)


def recent_lines(tracker: EscapeTracker) -> str:
    """Past justifications as the user wrote them: date, reason, explanation."""
    return "\n".join(
        f"{entry.get('date', '')}  {entry.get('reason', '')}: "
        f"{str(entry.get('description', ''))[:120]}"
        for entry in tracker.recent_justifications()
    )


def _field(parent: tk.Misc, config: LockConfig, glyph: str) -> tk.Frame:
    """One row: a glyph on the left, the input to its right."""
    row = tk.Frame(parent, bg=config.palette.field_bg)
    row.pack(fill="x", padx=config.space("md"), pady=config.space("xs"))
    tk.Label(
        row,
        text=glyph,
        font=config.font("title"),
        fg=config.palette.muted,
        bg=config.palette.field_bg,
        width=2,
    ).pack(side="left", anchor="n")
    return row


def build_escape_form(
    parent: tk.Misc,
    config: LockConfig,
    tracker: EscapeTracker,
    on_submit: Callable[[], bool],
) -> EscapeForm:
    """Build the form over ``parent`` and return its widgets."""
    palette = config.palette
    frame = tk.Frame(parent, bg=palette.field_bg)
    frame.place(relx=0.5, rely=0.5, anchor="center")

    tk.Label(
        frame,
        text=budget_marks(tracker),
        font=config.font("title"),
        fg=palette.danger,
        bg=palette.field_bg,
    ).pack(padx=config.space("md"), pady=(config.space("md"), config.space("sm")))

    reason = tk.Entry(
        _field(frame, config, "✎"), width=60, bg=palette.bg, fg=palette.fg
    )
    reason.pack(side="left", fill="x", expand=True)
    onset = tk.Entry(_field(frame, config, "◷"), width=60, bg=palette.bg, fg=palette.fg)
    onset.pack(side="left", fill="x", expand=True)
    description = tk.Text(
        _field(frame, config, "¶"), width=60, height=6, bg=palette.bg, fg=palette.fg
    )
    description.pack(side="left", fill="x", expand=True)

    minimum = tracker.policy.justification_min_chars
    counter = tk.Label(
        frame,
        text=f"0/{minimum}",
        font=config.font("caption"),
        fg=palette.danger,
        bg=palette.field_bg,
    )
    counter.pack(anchor="e", padx=config.space("md"))

    def count(_event: object = None) -> None:
        written = len(description.get("1.0", "end").strip())
        colour = palette.success if written >= minimum else palette.danger
        counter.configure(text=f"{written}/{minimum}", fg=colour)

    description.bind("<KeyRelease>", count)

    recent = recent_lines(tracker)
    if recent:
        tk.Label(
            frame,
            text=recent,
            font=config.font("caption"),
            fg=palette.muted,
            bg=palette.field_bg,
            justify="left",
            wraplength=700,
        ).pack(padx=config.space("md"), pady=config.space("xs"))

    complaint = tk.Label(
        frame,
        text="",
        font=config.font("title"),
        fg=palette.danger,
        bg=palette.field_bg,
    )
    complaint.pack(padx=config.space("md"), pady=config.space("xs"))

    submit = tk.Button(
        frame,
        text=g.SUBMIT,
        font=config.font("title"),
        width=3,
        fg=palette.on_fill,
        bg=palette.warning,
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
        counter=counter,
    )


def flag_refusal(form: EscapeForm, draft: EscapeDraft, config: LockConfig) -> None:
    """Show a refusal without words: a warning mark, and the field outlined.

    Mirrors ``EscapeTracker.validate``'s order (reason, onset, length) from
    the draft itself rather than parsing gatelock's sentence.
    """
    if not draft.reason:
        field = form.reason
    elif not draft.onset:
        field = form.onset
    else:
        field = form.description
    if form.flagged is not None and form.flagged is not field:
        form.flagged.configure(highlightthickness=0)
    field.configure(
        highlightthickness=_HIGHLIGHT_PX,
        highlightbackground=config.palette.danger,
        highlightcolor=config.palette.danger,
    )
    form.flagged = field
    form.complaint.configure(text=g.BLIND)
