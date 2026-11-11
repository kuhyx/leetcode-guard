"""Wire study mode into the lock: the Open button, the strip, the way back.

Split out of ``_lock.py`` for the 400-line cap, and like ``ReleaseMixin`` it is
the right seam anyway -- this is the whole "let them actually reach a problem"
surface in one place, which is the part worth reading before changing anything
about the 2026-08-05 fix.

The ordering that matters is in :meth:`StudyMixin.open_problem`: **find the
browser before touching the grab.** The common failure is having no browser
installed at all, and discovering that after standing the lock down would leave
the machine unguarded for nothing. A lock weakened for a browser that never
starts is strictly worse than a lock that says it could not open one.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final

from leetcode_guard import _glyphs as g
from leetcode_guard._browser import find_opener, launch
from leetcode_guard._study import StudySession
from leetcode_guard._study_strip import build_strip
from leetcode_guard._study_strip_text import StripText

if TYPE_CHECKING:
    from gatelock import OutputRect

    from leetcode_guard._gate import GateDecision
    from leetcode_guard._lock_state import RunState
    from leetcode_guard._study_strip import StudyStrip
    from leetcode_guard._view_group import FrameGroup

_logger: Final = logging.getLogger(__name__)


class StudyMixin:
    """Study mode, mixed into the lock.

    Owns ``_study`` and ``_strip`` (``None`` until a session starts) and reads
    ``_frames``, ``_run`` and ``_lock`` from the class it is mixed into.
    Declared rather than assumed, for the reason ``ReleaseMixin`` gives: a mixin
    that quietly expects attributes breaks on a
    refactor and says nothing until runtime.
    """

    _study: StudySession | None = None
    strip: StudyStrip | None = None
    frames: FrameGroup
    run_state: RunState
    lock: Any
    nudge_verifying: bool
    nudge_down: bool

    def decision(self) -> GateDecision:
        """Provided by the host class."""
        raise NotImplementedError

    # -- entering ---------------------------------------------------------

    def open_problem(self, url: str) -> None:
        """Open one problem, standing the lock down so it can be used.

        Order is deliberate and each step can refuse:

        1. Resolve a browser **without spawning**. No browser means no suspend.
        2. Suspend. A failure leaves the lock fully asserted and stops here.
        3. Spawn for real. A failure here rolls the suspend back.
        4. Show the strip.
        """
        if find_opener() is None:
            self._say("no browser launcher found", url=url)
            _logger.warning("no browser to open %s with; the lock is unchanged", url)
            return

        session = self.session()
        if session.active:
            # A second problem while already studying is a legitimate thing to
            # want. Nothing to tear down, and the elapsed clock keeps running.
            self._spawn(url)
            return

        outcome = session.suspend()
        if not outcome.ok:
            self._say(f"could not stand the lock down ({outcome.reason})")
            return

        if not self._spawn(url):
            # Nothing to study with, so do not leave the machine open.
            session.resume()
            return

        self._show_strip()

    def _spawn(self, url: str) -> bool:
        """Launch the browser, reporting failure on the surface.

        Guarded even though :func:`launch` promises not to raise: this is called
        with the grab already released, so anything escaping here skips the
        rollback and leaves the machine open. A promise one module makes is not
        a guarantee the caller of a *lock* should bet the screen on.
        """
        try:
            result = launch(url)
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.exception("the browser launcher raised; treating as a failure")
            self._say("the browser launcher raised", url=url)
            return False
        if not result.ok:
            self._say(f"could not open a browser ({result.reason})", url=url)
        return result.ok

    def _show_strip(self) -> None:
        """Put the study strip up on the primary output, if there is one."""
        rect = self.primary_rect()
        if rect is None:
            # Zero live outputs: nothing to place it on. The poller still runs
            # and a real solve still unlocks, so this is a degraded study
            # session rather than a broken one.
            _logger.warning("no output to place the study strip on")
            return
        self.strip = build_strip(
            self.lock.root,
            self.run_state.config,
            self.strip_text(),
            rect=rect,
            on_back=self.back_to_lock,
        )
        self.strip.schedule(self.strip_text)

    def primary_rect(self) -> OutputRect | None:
        """The primary output's rectangle, or the first, or ``None``."""
        infos = self.lock.surfaces.infos()
        if not infos:
            return None
        for info in infos:
            if info.is_primary:
                return info.rect
        return infos[0].rect

    def strip_text(self) -> StripText:
        """What the strip should say right now."""
        session = self.session()
        return StripText(
            elapsed_seconds=session.elapsed_seconds(),
            needed=max(1, self.decision().needed),
            verifying=self.nudge_verifying,
            fast_path_down=self.nudge_down,
        )

    def refresh_strip(self) -> None:
        """Repaint the strip now, not on its next one-second tick."""
        if self.strip is not None:
            self.strip.tick(self.strip_text())

    # -- leaving ----------------------------------------------------------

    def back_to_lock(self) -> None:
        """Put the lock back, by request."""
        self._end_study()

    def _end_study(self) -> bool:
        """Tear the strip down and re-assert the lock.

        Returns:
            Whether study mode was running. The strip is always destroyed
            *before* the resume, so a stale tick can never fire against a
            re-grabbed screen.
        """
        session = self.session()
        if not session.active:
            return False
        self.drop_strip()
        outcome = session.resume()
        if not outcome.ok:
            self._say("the lock is back but could not re-take the input grab")
        return True

    def drop_strip(self) -> None:
        """Destroy the strip if there is one."""
        if self.strip is None:
            return
        self.strip.destroy()
        self.strip = None

    # -- helpers ----------------------------------------------------------

    def session(self) -> StudySession:
        """The study session, built on first use."""
        if self._study is None:
            self._study = StudySession(
                self.lock,
                self.run_state.config,
                on_fail_closed=self._say,
            )
        return self._study

    def _say(self, message: str, *, url: str = "") -> None:
        """Mark a failure on every surface's status line; log the sentence.

        The same channel ``on_callback_error`` uses: when something goes wrong
        while the lock is up, the screen is the only place the user is looking.
        No words there (textgate): a warning mark in the danger colour, plus
        the problem's URL when it could not be opened -- something the user
        can still type into a browser by hand.
        """
        _logger.warning("study mode: %s %s", message, url)
        mark = f"{g.BLIND} {url}" if url else g.BLIND
        for view in self.frames.views.values():
            view.status_line.configure(
                text=mark, fg=self.run_state.config.palette.danger
            )
