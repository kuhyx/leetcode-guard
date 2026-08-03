"""Build one surface's widgets.

Pure painting: everything shown is handed in as a :class:`ViewModel`. Nothing
here fetches, decides or writes. A network call on the paint path would mean no
window at all when the network is down, and no window is itself the bypass.

Colours come from ``LockConfig``'s own defaults, which *are* the unified design
system -- no overrides. The one rule that needs care is ``on_fill``: text on an
accent/danger fill must be the dark ink, not the near-white ``fg``, or it lands
at ~2.5:1 contrast.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import tkinter as tk
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import LockConfig

    from leetcode_guard._viewmodel import ViewModel

_PAD = 16


@dataclass
class GuardView:
    """The widgets belonging to one output."""

    output_name: str
    container: Any
    headline: Any
    balance_line: Any
    status_line: Any
    notes_label: Any
    problem_labels: list[Any] = field(default_factory=list)
    problems_frame: Any = None
    escape_button: Any = None


def build_guard_view(
    parent: tk.Misc,
    config: LockConfig,
    model: ViewModel,
    *,
    output_name: str,
    on_escape: Callable[[], None] | None = None,
) -> GuardView:
    """Create the widget tree for one surface.

    Args:
        parent: The per-output surface gatelock created.
        config: Design tokens and colours.
        model: What to display right now.
        output_name: Which output this is, for bookkeeping.
        on_escape: Invoked when the escape hatch is pressed, if offered.

    Returns:
        Handles to every widget that later updates need to touch.
    """
    container = tk.Frame(parent, bg=config.bg)
    container.pack(expand=True, fill="both")

    inner = tk.Frame(container, bg=config.bg)
    inner.place(relx=0.5, rely=0.5, anchor="center")

    headline = tk.Label(
        inner,
        text=model.headline,
        font=config.font("display", bold=True),
        fg=config.fg,
        bg=config.bg,
    )
    headline.pack(pady=(0, _PAD))

    balance_line = tk.Label(
        inner,
        text=model.balance_line,
        font=config.font("subtitle"),
        fg=config.accent,
        bg=config.bg,
    )
    balance_line.pack(pady=(0, _PAD))

    problems_frame = tk.Frame(inner, bg=config.field_bg)
    problems_frame.pack(pady=(0, _PAD), padx=_PAD, fill="x")
    problem_labels = _build_problem_labels(problems_frame, config, model)

    status_line = tk.Label(
        inner,
        text=model.status_line,
        font=config.font("body"),
        fg=config.muted,
        bg=config.bg,
    )
    status_line.pack(pady=(0, _PAD // 2))

    notes_label = tk.Label(
        inner,
        text="\n".join(model.notes),
        font=config.font("caption"),
        fg=config.muted,
        bg=config.bg,
        justify="center",
        wraplength=900,
    )
    notes_label.pack()

    view = GuardView(
        output_name=output_name,
        container=container,
        headline=headline,
        balance_line=balance_line,
        status_line=status_line,
        notes_label=notes_label,
        problem_labels=problem_labels,
        problems_frame=problems_frame,
    )

    if on_escape is not None:
        view.escape_button = tk.Button(
            inner,
            text="I cannot do this right now",
            font=config.font("caption"),
            # on_fill, not fg: near-white on the danger fill measures about
            # 2.5:1, while the dark ink measures about 5.8:1.
            fg=config.on_fill,
            bg=config.danger,
            command=on_escape,
            relief="flat",
        )
        view.escape_button.pack(pady=(_PAD, 0))
        if not model.show_escape:
            view.escape_button.pack_forget()

    return view


def _build_problem_labels(
    parent: tk.Misc, config: LockConfig, model: ViewModel
) -> list[Any]:
    """Render the suggestion list, or a stand-in when there isn't one."""
    if not model.problems:
        placeholder = tk.Label(
            parent,
            text="Solve any LeetCode problem -- any accepted submission counts.",
            font=config.font("body"),
            fg=config.fg,
            bg=config.field_bg,
            anchor="w",
        )
        placeholder.pack(fill="x", padx=_PAD, pady=_PAD // 2)
        return [placeholder]

    labels = []
    for line in model.problems:
        label = tk.Label(
            parent,
            text=f"{line.label}\n{line.url}",
            font=config.font("body"),
            fg=config.fg,
            bg=config.field_bg,
            anchor="w",
            justify="left",
        )
        label.pack(fill="x", padx=_PAD, pady=_PAD // 4)
        labels.append(label)
    return labels
