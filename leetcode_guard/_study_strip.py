"""The small window that stays up while the lock is stood down.

Study mode hides every lock surface, so without this the screen would simply
clear and the re-lock would arrive out of nowhere. The strip keeps the gate
present: how many credits are earned today (filled dots), how many are still
owed (hollow dots), and the way back.

**No time at all** (kuhy, 2026-11-22: time in exactly one place, and it is not
here). There is no clock and no countdown -- study mode has no deadline, it
ends on a verified solve or on the button below, and a timer would invent a
pressure the gate does not apply. The window has no fixed height: it takes it
from its contents, so a verdict line that is absent leaves no gap and a grid of
many dots wraps without being clipped (:mod:`leetcode_guard._strip_dots`).

Staying on top is this window's own job. gatelock's ``RecoveryLoop`` is stopped
for the duration -- it is what would otherwise re-take the grab -- so nothing
else is re-lifting anything. The one-second tick therefore calls ``lift()``
(and repaints the dots if a count moved). Deliberately *not* a second recovery
loop: re-asserting the grab is precisely what must not happen here.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import tkinter as tk
from typing import TYPE_CHECKING, Final

from leetcode_guard import _glyphs as g
from leetcode_guard._constants import STUDY_STRIP_TICK_MS, STUDY_STRIP_WIDTH_PX
from leetcode_guard._strip_dots import DotPainter
from leetcode_guard._tooltip import add_tooltip

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from gatelock import LockConfig, OutputRect, SurfaceInfo

    from leetcode_guard._study_strip_text import StripText

_logger: Final = logging.getLogger(__name__)

_TOPMOST_ON = 1


@dataclass(frozen=True)
class StripTitle:
    """The heading label and its two colours (normal, instant check down)."""

    label: tk.Label
    normal: str
    warn: str


class StudyStrip:
    """A always-on-top status strip, owned by the study session."""

    def __init__(
        self,
        window: tk.Toplevel,
        headline_label: tk.Label,
        dots: DotPainter,
        *,
        title: StripTitle | None = None,
        tick_ms: int = STUDY_STRIP_TICK_MS,
    ) -> None:
        """Wrap an already-built strip window."""
        self.window = window
        self._title = title
        self._headline_label = headline_label
        self._dots = dots
        self._headline_shown = False
        self._tick_ms = tick_ms
        self._job: str | None = None
        self._destroyed = False

    def tick(self, text: StripText) -> None:
        """Refresh the labels and re-assert stacking."""
        if self._destroyed:
            return
        try:
            if (title := self._title) is not None:
                title.label.configure(
                    text=text.title,
                    fg=title.warn if text.fast_path_down else title.normal,
                )
            self._show_headline(text.headline)
            self._dots.paint(text.filled, text.hollow)
            self.window.lift()
        except tk.TclError:
            # A browser going fullscreen over us is cosmetic; a raised
            # exception inside a Tk callback is not. Stop ticking and say so.
            _logger.warning("the study strip could not refresh", exc_info=True)
            self._destroyed = True

    def _show_headline(self, headline: str) -> None:
        """Write the verdict line, or take it off the window so it leaves no gap."""
        if headline:
            self._headline_label.configure(text=headline)
            if not self._headline_shown:
                self._headline_label.pack(before=self._dots.canvas)
                self._headline_shown = True
        elif self._headline_shown:
            self._headline_label.pack_forget()
            self._headline_shown = False

    def schedule(self, supply: Callable[[], StripText]) -> None:
        """Start the one-second tick that updates and re-lifts."""
        if self._destroyed:
            return

        def run() -> None:
            self.tick(supply())
            if not self._destroyed:
                self._job = self.window.after(self._tick_ms, run)

        self._job = self.window.after(self._tick_ms, run)

    def destroy(self) -> None:
        """Cancel the tick and tear the window down. Idempotent."""
        if self._destroyed:
            return
        self._destroyed = True
        try:
            if self._job is not None:
                self.window.after_cancel(self._job)
            self.window.destroy()
        except tk.TclError:
            _logger.warning("the study strip could not be destroyed", exc_info=True)


def build_strip(
    root: tk.Misc,
    config: LockConfig,
    text: StripText,
    *,
    rect: OutputRect,
    on_back: Callable[[], None],
) -> StudyStrip:
    """Create the strip on one output's rectangle.

    Args:
        root: The lock's Tk root, used as the parent.
        config: Design tokens.
        text: What to show immediately, so the strip is never blank.
        rect: The output rectangle to sit on -- the *primary surface's*, not the
            whole X screen, which on a multi-monitor desk spans every display
            and would park this on the far one.
        on_back: Invoked by the "Back to lock" button.

    Returns:
        The strip handle.
    """
    window = tk.Toplevel(root)
    # Creation order, matching gatelock's own: override-redirect must be set
    # while the window is withdrawn or the geometry below is ignored.
    window.withdraw()
    window.overrideredirect(boolean=True)
    window.configure(bg=config.palette.field_bg)
    window.geometry(_geometry(config, rect))
    window.deiconify()
    window.lift()
    # A hint most window managers honour even for override-redirect windows,
    # and harmless where they do not. Neither this nor `lift` is enough alone.
    window.attributes("-topmost", _TOPMOST_ON)

    title = tk.Label(
        window,
        text=text.title,
        font=config.font("label", bold=True),
        fg=config.palette.warning if text.fast_path_down else config.palette.fg,
        bg=config.palette.field_bg,
    )
    title.pack(pady=(config.space("sm"), 0))

    headline_label = tk.Label(
        window,
        text=text.headline,
        font=config.font("body"),
        fg=config.palette.accent,
        bg=config.palette.field_bg,
    )
    canvas = tk.Canvas(
        window,
        width=STUDY_STRIP_WIDTH_PX,
        height=0,
        bg=config.palette.field_bg,
        highlightthickness=0,
        bd=0,
    )
    dots = DotPainter(
        canvas,
        STUDY_STRIP_WIDTH_PX,
        filled_colour=config.palette.success,
        hollow_colour=config.palette.muted,
        check_font=config.font("body"),
    )
    canvas.pack(pady=(config.space("xs"), 0))

    back = tk.Button(
        window,
        text=g.BACK,
        font=config.font("body"),
        width=3,
        # accent, not danger: returning to the lock is the ordinary path, not a
        # destructive one. danger belongs to the escape hatch.
        fg=config.palette.on_fill,
        bg=config.palette.accent,
        command=on_back,
        relief="flat",
    )
    add_tooltip(back, "relock")
    back.pack(pady=(config.space("xs"), config.space("sm")))

    strip = StudyStrip(
        window,
        headline_label,
        dots,
        title=StripTitle(title, config.palette.fg, config.palette.warning),
    )
    strip.tick(text)
    return strip


def _geometry(config: LockConfig, rect: OutputRect) -> str:
    """Top-right of the given rectangle, inset by one spacing step.

    Top-right because the centre is where a browser puts the problem statement
    the user is trying to read, and the bottom-right is where desktop
    notifications land. Position only: the size is the contents' (a fixed one
    would clip a wrapped dot grid or leave a gap where the verdict line is not).
    """
    inset = config.space("md")
    x = rect.x + rect.width - STUDY_STRIP_WIDTH_PX - inset
    y = rect.y + inset
    return f"+{x}+{y}"


def pick_primary_rect(infos: Sequence[SurfaceInfo]) -> OutputRect | None:
    """The primary output's rectangle, or the first, or ``None`` if none."""
    for info in infos:
        if info.is_primary:
            return info.rect
    return infos[0].rect if infos else None
