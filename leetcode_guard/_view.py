"""Build one surface's widgets.

Pure painting: everything shown is handed in as a :class:`ViewModel`. Nothing
here fetches, decides or writes. A network call on the paint path would mean no
window at all when the network is down, and no window is itself the bypass.

Colours come from ``LockConfig``'s own defaults, which *are* the unified design
system -- no overrides. The one rule that needs care is ``on_fill``: text on an
accent/danger fill must be the dark ink, not the near-white ``fg``, or it lands
at ~2.5:1 contrast.

:func:`~leetcode_guard._breakglass.breakglass_lines` is called from the paint
path, which is not the exception to "pure painting" it looks like: it takes a
config and returns strings, touching no I/O and reaching no decision. The
invariant that matters -- a surface can always be drawn, whatever else is
broken -- still holds.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from leetcode_guard._breakglass import breakglass_lines
from leetcode_guard._constants import PROBLEM_DISPLAY_LIMIT
from leetcode_guard._view_problems import build_problem_rows
from leetcode_guard._view_scroll import ScrollArea, grow_rows
from leetcode_guard._view_types import GuardView, ProblemList, ViewHooks

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import LockConfig

    from leetcode_guard._viewmodel import ViewModel

_PAD = 16


def _label(parent: tk.Misc, config: LockConfig, text: str, *, font: str) -> tk.Label:
    """One centred, wrapped line of muted text in the lock's colours."""
    return tk.Label(
        parent,
        text=text,
        font=config.font(font),
        fg=config.palette.muted,
        bg=config.palette.bg,
        # Wrapped. An over-wide label on a place-centred frame shears off both
        # edges rather than clipping one, and these lines carry variable-length
        # text (an unverifiable probe's reason, the names of solves that freed
        # a row, the notes).
        justify="center",
        wraplength=900,
    )


def _build_problems(
    inner: tk.Misc,
    config: LockConfig,
    model: ViewModel,
    hooks: ViewHooks,
    grow: list[Callable[[], object]],
) -> ProblemList:
    """The scrolling suggestion list, with an Open button per row if wired."""
    scroll = ScrollArea(inner, config, on_near_end=lambda: [g() for g in grow])
    scroll.outer.pack(pady=(0, _PAD), padx=_PAD, fill="x")
    labels, buttons = build_problem_rows(
        scroll.inner, config, model, hooks.on_open, bind=scroll.bind_wheel
    )
    scroll.fit_rows(len(labels), PROBLEM_DISPLAY_LIMIT)
    return ProblemList(
        labels=labels,
        frame=scroll.inner,
        buttons=buttons,
        scroll=scroll,
        lines=model.problems,
    )


def _add_escape_button(
    view: GuardView, inner: tk.Misc, config: LockConfig, model: ViewModel
) -> None:
    """The hatch button, built whenever a hatch is wired and hidden if not due."""
    view.escape_button = tk.Button(
        inner,
        text="I cannot do this right now",
        font=config.font("caption"),
        # on_fill, not fg: near-white on the danger fill measures about
        # 2.5:1, while the dark ink measures about 5.8:1.
        fg=config.palette.on_fill,
        bg=config.palette.danger,
        command=view.hooks.on_escape,
        relief="flat",
    )
    view.escape_button.pack(pady=(_PAD, 0))
    if not model.show_escape:
        view.escape_button.pack_forget()


def build_guard_view(
    parent: tk.Misc,
    config: LockConfig,
    model: ViewModel,
    *,
    output_name: str,
    hooks: ViewHooks | None = None,
) -> GuardView:
    """Create the widget tree for one surface.

    Args:
        parent: The per-output surface gatelock created.
        config: Design tokens and colours.
        model: What to display right now.
        output_name: Which output this is, for bookkeeping.
        hooks: The callbacks the surface may invoke (escape, open, reveal);
            ``None`` renders the list as inert text and builds no hatch.

    Returns:
        Handles to every widget that later updates need to touch.
    """
    hooks = hooks if hooks is not None else ViewHooks()
    container = tk.Frame(parent, bg=config.palette.bg)
    container.pack(expand=True, fill="both")

    inner = tk.Frame(container, bg=config.palette.bg)
    inner.place(relx=0.5, rely=0.5, anchor="center")

    headline = tk.Label(
        inner,
        text=model.headline,
        font=config.font("display", bold=True),
        fg=config.palette.fg,
        bg=config.palette.bg,
    )
    headline.pack(pady=(0, _PAD))

    balance_line = tk.Label(
        inner,
        text=model.balance_line,
        font=config.font("subtitle"),
        fg=config.palette.accent,
        bg=config.palette.bg,
    )
    balance_line.pack(pady=(0, _PAD))

    grow: list[Callable[[], object]] = []
    problems = _build_problems(inner, config, model, hooks, grow)

    status_line = _label(inner, config, model.status_line, font="body")
    status_line.pack(pady=(0, _PAD // 2))

    notes_label = _label(inner, config, "\n".join(model.notes), font="caption")
    notes_label.pack()

    # Permanent, and never unpacked. This is the only instruction on the screen
    # that keeps working when everything else in this package is wrong, and its
    # absence is why the 2026-08-05 lockout needed a terminal that happened to
    # already be open. `apply_viewmodel` does not touch it, so no repaint can
    # quietly hide it.
    breakglass_label = _label(
        inner, config, "\n".join(breakglass_lines(config)), font="caption"
    )
    breakglass_label.pack(pady=(_PAD, 0))

    view = GuardView(
        output_name=output_name,
        container=container,
        headline=headline,
        balance_line=balance_line,
        status_line=status_line,
        notes_label=notes_label,
        breakglass_label=breakglass_label,
        problems=problems,
        hooks=hooks,
    )
    grow.append(lambda: grow_rows(view, config))

    if hooks.on_escape is not None:
        _add_escape_button(view, inner, config, model)

    return view


def install_demo_close_button(
    parent: tk.Misc, config: LockConfig, on_close: Callable[[], None]
) -> tk.Button:
    """The escape that makes a demo safe to run.

    Installed on the **surface**, not on the root. With
    ``overrideredirect=True`` the root is a full-screen backdrop and gatelock's
    per-output Toplevels sit on top of it, so a button placed on the root is
    drawn behind them and is invisible and unclickable. Caught by screenshotting
    the demo rather than by any test -- which is exactly why the demo gets
    screenshotted.
    """
    button = tk.Button(
        parent,
        text="X Close Demo",
        fg=config.palette.on_fill,
        bg=config.palette.danger,
        command=on_close,
        relief="flat",
    )
    button.place(x=10, y=10)
    return button
