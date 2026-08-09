"""The small window that stays up while the lock is stood down.

Study mode hides every lock surface, so without this the screen would simply
clear and the re-lock would arrive out of nowhere. The strip keeps the gate
present: how long you have been at it, how many solves are still owed, and the
way back.

**No countdown.** There is no deadline to count down to -- study mode ends on a
verified solve or on the button below, and nothing else. Showing a timer would
be inventing a pressure the gate does not actually apply, and the tests assert
the absence of "remaining", "left" and "until" for exactly that reason.

Staying on top is this window's own job. gatelock's ``RecoveryLoop`` is stopped
for the duration -- it is what would otherwise re-take the grab -- so nothing
else is re-lifting anything. The one-second tick that refreshes the elapsed
label therefore also calls ``lift()``. Deliberately *not* a second recovery
loop: re-asserting the grab is precisely what must not happen here.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import tkinter as tk
from typing import TYPE_CHECKING, Final

from leetcode_guard._constants import (
    STUDY_STRIP_HEIGHT_PX,
    STUDY_STRIP_TICK_MS,
    STUDY_STRIP_WIDTH_PX,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import LockConfig, OutputRect

_logger: Final = logging.getLogger(__name__)

_TOPMOST_ON = 1


@dataclass
class StripText:
    """What the strip currently says."""

    elapsed_seconds: float
    needed: int

    @property
    def elapsed(self) -> str:
        """``Studying for MM:SS`` -- elapsed only, never a target."""
        total = max(0, int(self.elapsed_seconds))
        return f"Studying for {total // 60:02d}:{total % 60:02d}"

    @property
    def owed(self) -> str:
        """How many accepted submissions are still outstanding."""
        if self.needed == 1:
            return "Still need 1 accepted submission"
        return f"Still need {self.needed} accepted submissions"


class StudyStrip:
    """A always-on-top status strip, owned by the study session."""

    def __init__(
        self,
        window: tk.Toplevel,
        elapsed_label: tk.Label,
        needed_label: tk.Label,
        *,
        tick_ms: int = STUDY_STRIP_TICK_MS,
    ) -> None:
        """Wrap an already-built strip window."""
        self.window = window
        self._elapsed_label = elapsed_label
        self._needed_label = needed_label
        self._tick_ms = tick_ms
        self._job: str | None = None
        self._destroyed = False

    def tick(self, text: StripText) -> None:
        """Refresh the labels and re-assert stacking."""
        if self._destroyed:
            return
        try:
            self._elapsed_label.configure(text=text.elapsed)
            self._needed_label.configure(text=text.owed)
            self.window.lift()
        except tk.TclError:
            # A browser going fullscreen over us is cosmetic; a raised
            # exception inside a Tk callback is not. Stop ticking and say so.
            _logger.warning("the study strip could not refresh", exc_info=True)
            self._destroyed = True

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
    window.configure(bg=config.field_bg)
    window.geometry(_geometry(config, rect))
    window.deiconify()
    window.lift()
    # A hint most window managers honour even for override-redirect windows,
    # and harmless where they do not. Neither this nor `lift` is enough alone.
    window.attributes("-topmost", _TOPMOST_ON)

    title = tk.Label(
        window,
        text="Study mode -- the lock is waiting",
        font=config.font("label", bold=True),
        fg=config.fg,
        bg=config.field_bg,
    )
    title.pack(pady=(config.space("sm"), 0))

    elapsed_label = tk.Label(
        window,
        text=text.elapsed,
        font=config.font("body"),
        fg=config.accent,
        bg=config.field_bg,
    )
    elapsed_label.pack()

    needed_label = tk.Label(
        window,
        text=text.owed,
        font=config.font("caption"),
        fg=config.muted,
        bg=config.field_bg,
    )
    needed_label.pack()

    back = tk.Button(
        window,
        text="Back to lock",
        font=config.font("caption"),
        # accent, not danger: returning to the lock is the ordinary path, not a
        # destructive one. danger belongs to the escape hatch.
        fg=config.on_fill,
        bg=config.accent,
        command=on_back,
        relief="flat",
    )
    back.pack(pady=(config.space("xs"), config.space("sm")))

    return StudyStrip(window, elapsed_label, needed_label)


def _geometry(config: LockConfig, rect: OutputRect) -> str:
    """Top-right of the given rectangle, inset by one spacing step.

    Top-right because the centre is where a browser puts the problem statement
    the user is trying to read, and the bottom-right is where desktop
    notifications land.
    """
    inset = config.space("md")
    width = STUDY_STRIP_WIDTH_PX
    height = STUDY_STRIP_HEIGHT_PX
    x = rect.x + rect.width - width - inset
    y = rect.y + inset
    return f"{width}x{height}+{x}+{y}"
