"""The records one surface's widgets are kept in.

Split from ``_view.py`` for the 250-line cap, and because it imports no tkinter:
the updaters and tests that only read a surface need not pull the toolkit in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from leetcode_guard._viewmodel import ProblemLine


@dataclass
class ProblemList:
    """The scrolling suggestion list: its widgets and what they were painted from."""

    labels: list[Any] = field(default_factory=list)
    frame: Any = None
    buttons: list[Any] = field(default_factory=list)
    scroll: Any = None
    lines: tuple[ProblemLine, ...] = ()
    """What the rows were last painted from; rows built on scroll read it."""
    marks: list[Any] = field(default_factory=list)
    """Each row's weight-mark label (``◆◆  48%``), in list order."""


@dataclass
class RowWiring:
    """What every new suggestion row is hooked up to."""

    bind: Callable[[Any], None] | None = None
    """Called on every new widget, so the wheel scrolls over it."""
    marks: list[Any] = field(default_factory=list)
    """Receives each row's weight-mark label, so a repaint can move a new
    problem's mark (and its colour) into a reused row."""


@dataclass(frozen=True)
class ViewHooks:
    """What the surface can call back into; each ``None`` renders it inert."""

    on_open: Callable[[str], None] | None = None
    """Invoked with a problem's URL when its Open button is pressed.

    Retained on the view so a repaint can re-bind a row to a different problem:
    each button's command closes over the URL it was built with, so promoting a
    problem into a freed slot without rebinding would leave an Open button
    pointing at the problem that was just solved. ``None`` renders the list as
    inert text, which is what the fit harness and any read-only render want --
    and what the lock itself did on 2026-08-05, when naming ten problems it
    would accept and offering no way to reach one made it unsatisfiable.
    """

    on_reveal: Callable[[int], None] | None = None
    """Told how many rows exist after the list grows, so they can be verified."""

    on_escape: Callable[[], None] | None = None
    """Invoked when the escape hatch is pressed; ``None`` builds no button."""


@dataclass
class SurfaceDecor:
    """The parts of a surface no repaint rewrites the text of."""

    padlock: Any = None
    """The drawn padlock beside the headline (``_view_icons.Padlock``);
    repaints only redraw its state."""
    breakglass: Any = None
    """The permanent recovery-route label; never unpacked, never rewritten."""
    config: Any = None
    """The ``LockConfig`` the surface was built with, for colours on repaint."""


@dataclass
class GuardView:
    """The widgets belonging to one output."""

    output_name: str
    container: Any
    headline: Any
    balance_line: Any
    status_line: Any
    notes_label: Any
    escape_button: Any = None
    decor: SurfaceDecor = field(default_factory=SurfaceDecor)
    problems: ProblemList = field(default_factory=ProblemList)
    hooks: ViewHooks = field(default_factory=ViewHooks)
