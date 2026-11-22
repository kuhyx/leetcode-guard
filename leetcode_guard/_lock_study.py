"""Wire study mode into the lock: the Open button, the strip, the way back.

Split out of ``_lock.py``; like ``ReleaseMixin`` it is the right seam anyway: the
whole "let them actually reach a problem" surface (the 2026-08-05 fix) in one place.

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
from leetcode_guard._lock_learn import LearnButton, rework_route_for
from leetcode_guard._study import StudySession
from leetcode_guard._study_restart import forget_study, remember_study
from leetcode_guard._study_strip import build_strip
from leetcode_guard._study_strip_text import StripText

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import OutputRect

    from leetcode_guard._gate import GateDecision
    from leetcode_guard._lock_deps import GuardDeps
    from leetcode_guard._lock_state import RunState
    from leetcode_guard._study_strip import StudyStrip
    from leetcode_guard._view_group import FrameGroup
    from leetcode_guard._viewmodel import ViewModel

_logger: Final = logging.getLogger(__name__)


class StudyMixin:
    """Study mode, mixed into the lock.

    Owns ``_study`` and ``_strip`` (``None`` until a session starts) and reads
    the attributes below from the class it is mixed into, declared rather than
    assumed (``ReleaseMixin``: a silent expectation breaks only at runtime).
    """

    _study: StudySession | None = None
    strip: StudyStrip | None = None
    _strip_needed: int | None = None
    # The 1 s strip tick reuses the last decide_today answer (~35 ms and
    # dozens of pool reads on the Tk thread) until refresh_strip() asks again.
    frames: FrameGroup
    run_state: RunState
    deps: GuardDeps
    model: ViewModel
    lock: Any
    nudge_verifying: bool
    nudge_down: bool
    remembers_study: bool = True  # ``_study_restart``; the evening lock opts out

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
        self.enter_study(lambda: self._spawn(url))

    def open_learn(self, route: str) -> None:
        """The theory card's learn button; a ``LearnButton`` per press (no state)."""
        config = self.run_state.config
        LearnButton(self.enter_study, self._say, self.frames, config).open_learn(route)

    def open_rework(self, slug: str) -> None:
        """A SOLVE row's ``?``: the rework chat via the learn path (``_lock_learn``)."""
        if (route := rework_route_for(self.model.screen.rework, slug)) is not None:
            self.open_learn(route)

    def enter_study(self, spawn: Callable[[], bool]) -> None:
        """Steps 2-4 of :meth:`open_problem`, shared with the learn button.

        The caller has already resolved its launcher without spawning (step 1).
        ``spawn`` launches for real and reports success; a failure rolls the
        suspend back, because there is nothing to study with.
        """
        session = self.session()
        if session.active:
            # A second problem while already studying is a legitimate thing to
            # want. Nothing to tear down, and the elapsed clock keeps running.
            spawn()
            return

        outcome = session.suspend()
        if not outcome.ok:
            self._say(f"could not stand the lock down ({outcome.reason})")
            return

        if not spawn():
            # Nothing to study with, so do not leave the machine open.
            session.resume()
            return

        remember_study(self)
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
        self._strip_needed = None
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

    def _needed_for_strip(self) -> int:
        """Problems still owed, computed once per refresh, not per tick."""
        if self._strip_needed is None:
            self._strip_needed = max(1, self.decision().needed)
        return self._strip_needed

    def strip_text(self) -> StripText:
        """What the strip should say right now."""
        session = self.session()
        return StripText(
            elapsed_seconds=session.elapsed_seconds(),
            needed=self._needed_for_strip(),
            verifying=self.nudge_verifying,
            fast_path_down=self.nudge_down,
        )

    def refresh_strip(self) -> None:
        """Repaint the strip now, not on its next one-second tick."""
        self._strip_needed = None
        if self.strip is not None:
            self.strip.tick(self.strip_text())

    # -- leaving ----------------------------------------------------------

    def back_to_lock(self) -> None:
        """Put the lock back, by request."""
        self._end_study()

    def _end_study(self) -> bool:
        """End study for a real reason (Back to lock, a solve): forget it too."""
        forget_study(self)
        return self.relock_study()

    def relock_study(self) -> bool:
        """Tear the strip down and re-assert the lock; the marker stays.

        Returns:
            Whether study mode was running. The strip goes *before* the resume,
            so a stale tick never fires against a re-grabbed screen.
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

        The channel ``on_callback_error`` uses; no words (textgate): a warning
        mark in the danger colour, plus the problem's URL when it could not be
        opened, which the user can still type into a browser by hand.
        """
        _logger.warning("study mode: %s %s", message, url)
        mark = f"{g.BLIND} {url}" if url else g.BLIND
        for view in self.frames.views.values():
            view.status_line.configure(
                text=mark, fg=self.run_state.config.palette.danger
            )
