"""Paint the THEORY card and the SOLVE bar (the data is ``_viewmodel_phase``).

Pure painting, like the rest of the view: the press is handed in, nothing here
reads a file or decides a phase.

Both widgets are built on every surface, once, in a slot frame packed between
the header and the suggestion list, and a screen change only packs or forgets
them. Building them lazily on the first THEORY would mean a rebuild mid-lock;
toggling the slot itself would re-pack it at the end of its parent, below the
break-glass.

The learn button is the largest control on a THEORY screen on purpose (the
display font, beside the card): kuhy's words are "first we learn ... and then
we can solve it", so the lesson is the first action, Open the second.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from leetcode_guard import _glyphs as g
from leetcode_guard._view_types import PhaseWidgets, UnitBar

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from gatelock import LockConfig

    from leetcode_guard._view_types import GuardView
    from leetcode_guard._viewmodel_phase import PhaseScreen, TheoryCard

_PAD = 16
_BAR_UNITS = 12
"""The taught / total bar is this many ``xl`` spacing steps wide."""


def _bar_size(config: LockConfig) -> tuple[int, int]:
    return config.space("xl") * _BAR_UNITS, config.space("sm") + config.space("xs")


def _label(
    parent: tk.Misc,
    config: LockConfig,
    *,
    font: tuple[str, int, str] | tuple[str, int],
    fg: str,
) -> tk.Label:
    return tk.Label(parent, text="", font=font, fg=fg, bg=config.palette.field_bg)


def _build_card(slot: tk.Misc, config: LockConfig, widgets: PhaseWidgets) -> None:
    """The card: pencil + unit, the taught bar, the rate, the learn button."""
    palette = config.palette
    card = tk.Frame(
        slot, bg=palette.field_bg, padx=config.space("lg"), pady=config.space("md")
    )
    text = tk.Frame(card, bg=palette.field_bg)
    text.pack(side="left", fill="x", expand=True)
    head = tk.Frame(text, bg=palette.field_bg)
    head.pack(anchor="w")
    widgets.title = _label(
        head, config, font=config.font("title", bold=True), fg=palette.fg
    )
    widgets.title.pack(side="left")
    widgets.ready_mark = _label(
        head, config, font=config.font("title", bold=True), fg=palette.warning
    )
    widgets.ready_mark.pack(side="left", padx=(config.space("md"), 0))
    meter = tk.Frame(text, bg=palette.field_bg)
    meter.pack(anchor="w", pady=config.space("sm"))
    width, height = _bar_size(config)
    widgets.progress = tk.Canvas(
        meter, width=width, height=height, bg=palette.bg, highlightthickness=0
    )
    widgets.progress.pack(side="left")
    widgets.counts = _label(meter, config, font=config.font("subtitle"), fg=palette.fg)
    widgets.counts.pack(side="left", padx=(config.space("md"), 0))
    widgets.rate = _label(text, config, font=config.font("body"), fg=palette.accent)
    widgets.rate.pack(anchor="w")
    widgets.learn = tk.Button(
        card,
        text=g.LEARN,
        font=config.font("display", bold=True, scale=1.5),
        width=4,
        # on_fill on an accent fill, as for Open (``_view`` module note).
        fg=palette.on_fill,
        bg=palette.accent,
        relief="flat",
    )
    widgets.learn.pack(side="right", padx=(config.space("lg"), 0))
    widgets.card = card


def _build_bar(slot: tk.Misc, config: LockConfig, widgets: PhaseWidgets) -> None:
    """The SOLVE bar: a check in the success colour, the unit, solved / total."""
    palette = config.palette
    frame = tk.Frame(
        slot, bg=palette.field_bg, padx=config.space("md"), pady=config.space("xs")
    )
    check = _label(
        frame, config, font=config.font("subtitle", bold=True), fg=palette.success
    )
    check.configure(text=g.SOLVED)
    check.pack(side="left")
    label = _label(frame, config, font=config.font("subtitle"), fg=palette.fg)
    label.pack(side="left", padx=(config.space("md"), 0))
    widgets.unit_bar = UnitBar(frame=frame, label=label)


def build_phase_slot(
    parent: tk.Misc,
    config: LockConfig,
    screen: PhaseScreen,
    on_learn: Callable[[str], None] | None,
) -> PhaseWidgets:
    """Build the slot, the card and the bar, and paint ``screen`` into them."""
    slot = tk.Frame(parent, bg=config.palette.bg)
    slot.pack(fill="x")
    widgets = PhaseWidgets(slot=slot)
    _build_card(slot, config, widgets)
    _build_bar(slot, config, widgets)
    paint_phase(widgets, config, screen, on_learn)
    return widgets


def _draw_progress(widgets: PhaseWidgets, config: LockConfig, card: TheoryCard) -> None:
    """Fill the bar to ``card.fraction``; unknown or empty stays an empty track."""
    widgets.progress.delete("all")
    if card.fraction is None or card.fraction <= 0:
        return
    width, height = _bar_size(config)
    widgets.progress.create_rectangle(
        0, 0, round(width * card.fraction), height, fill=config.palette.accent, width=0
    )


def _paint_card(
    widgets: PhaseWidgets,
    config: LockConfig,
    card: TheoryCard,
    on_learn: Callable[[str], None] | None,
) -> None:
    widgets.title.configure(text=card.title)
    widgets.ready_mark.configure(text=card.ready_mark)
    widgets.counts.configure(text=card.counts)
    widgets.rate.configure(text=card.rate)
    _draw_progress(widgets, config, card)
    route = card.route
    if route is None:
        widgets.learn.pack_forget()
        return
    # Default argument, as for Open: the route this screen names, not the
    # one the button was built with -- after SOLVE -> THEORY(next) the old
    # route would teach the finished unit.
    command = (lambda r=route: on_learn(r)) if on_learn is not None else ""
    widgets.learn.configure(text=card.button, bg=config.palette.accent, command=command)
    widgets.learn.pack(side="right", padx=(config.space("lg"), 0))


def paint_phase(
    widgets: PhaseWidgets,
    config: LockConfig,
    screen: PhaseScreen,
    on_learn: Callable[[str], None] | None,
) -> None:
    """Show the card, the bar or neither; an unchanged screen is left alone."""
    if widgets.painted == screen:
        return
    widgets.painted = screen
    unit_bar = widgets.unit_bar
    if screen.card is not None:
        unit_bar.frame.pack_forget()
        _paint_card(widgets, config, screen.card, on_learn)
        widgets.card.pack(fill="x", padx=_PAD, pady=(0, _PAD))
        return
    widgets.card.pack_forget()
    if not screen.unit_bar:
        unit_bar.frame.pack_forget()
        return
    unit_bar.label.configure(text=screen.unit_bar)
    unit_bar.frame.pack(fill="x", padx=_PAD, pady=(0, _PAD // 2))


def mark_learn_unavailable(views: Iterable[GuardView], config: LockConfig) -> int:
    """The "cannot open" state: the no-entry glyph on the danger fill.

    Stays until the screen changes (``paint_phase`` skips an unchanged screen),
    so a missing tutor is not papered over by the next poll's repaint.

    Returns:
        How many buttons were marked.
    """
    count = 0
    for view in views:
        if view.phase is None:
            continue
        view.phase.learn.configure(text=g.NO_ENTRY, bg=config.palette.danger)
        count += 1
    return count
