"""Wire study mode into the lock: the Open button, the strip, the way back.

Split out of ``_lock.py`` for the 400-line cap, and like ``ReleaseMixin`` it is
the right seam anyway -- this is the whole "let them actually reach a problem"
surface in one place, which is the part worth reading before changing anything
about the 2026-08-05 fix.

The ordering that matters is in :meth:`StudyMixin._open_problem`: **find the
browser before touching the grab.** The common failure is having no browser
installed at all, and discovering that after standing the lock down would leave
the machine unguarded for nothing. A lock weakened for a browser that never
starts is strictly worse than a lock that says it could not open one.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final

from leetcode_guard._browser import find_opener, launch
from leetcode_guard._study import StudySession
from leetcode_guard._study_strip import StripText, build_strip

if TYPE_CHECKING:
    from gatelock import LockConfig, OutputRect

    from leetcode_guard._gate import GateDecision
    from leetcode_guard._study_strip import StudyStrip
    from leetcode_guard._view import GuardView

_logger: Final = logging.getLogger(__name__)


class StudyMixin:
    """Study mode, mixed into the lock.

    Reads ``_study``, ``_strip``, ``_views``, ``_config`` and ``_lock`` from the
    class it is mixed into. Declared rather than assumed, for the reason
    ``ReleaseMixin`` gives: a mixin that quietly expects attributes breaks on a
    refactor and says nothing until runtime.
    """

    _study: StudySession | None
    _strip: StudyStrip | None
    _views: dict[str, GuardView]
    _config: LockConfig
    _lock: Any

    def _decision(self) -> GateDecision:
        """Provided by the host class."""
        raise NotImplementedError

    # -- entering ---------------------------------------------------------

    def _open_problem(self, url: str) -> None:
        """Open one problem, standing the lock down so it can be used.

        Order is deliberate and each step can refuse:

        1. Resolve a browser **without spawning**. No browser means no suspend.
        2. Suspend. A failure leaves the lock fully asserted and stops here.
        3. Spawn for real. A failure here rolls the suspend back.
        4. Show the strip.
        """
        if find_opener() is None:
            self._say(
                "No browser launcher found, so this problem cannot be opened "
                f"from here. Solve it at {url}"
            )
            _logger.warning("no browser to open %s with; the lock is unchanged", url)
            return

        session = self._session()
        if session.active:
            # A second problem while already studying is a legitimate thing to
            # want. Nothing to tear down, and the elapsed clock keeps running.
            self._spawn(url)
            return

        outcome = session.suspend()
        if not outcome.ok:
            self._say(f"Could not stand the lock down ({outcome.reason}).")
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
        except Exception:
            _logger.exception("the browser launcher raised; treating as a failure")
            self._say(f"Could not open a browser. Solve it at {url}")
            return False
        if not result.ok:
            self._say(f"Could not open a browser ({result.reason}). Solve it at {url}")
        return result.ok

    def _show_strip(self) -> None:
        """Put the study strip up on the primary output, if there is one."""
        rect = self._primary_rect()
        if rect is None:
            # Zero live outputs: nothing to place it on. The poller still runs
            # and a real solve still unlocks, so this is a degraded study
            # session rather than a broken one.
            _logger.warning("no output to place the study strip on")
            return
        self._strip = build_strip(
            self._lock.root,
            self._config,
            self._strip_text(),
            rect=rect,
            on_back=self._back_to_lock,
        )
        self._strip.schedule(self._strip_text)

    def _primary_rect(self) -> OutputRect | None:
        """The primary output's rectangle, or the first, or ``None``."""
        infos = self._lock.surfaces.infos()
        if not infos:
            return None
        for info in infos:
            if info.is_primary:
                return info.rect
        return infos[0].rect

    def _strip_text(self) -> StripText:
        """What the strip should say right now."""
        session = self._session()
        return StripText(
            elapsed_seconds=session.elapsed_seconds(),
            needed=max(1, self._decision().needed),
        )

    # -- leaving ----------------------------------------------------------

    def _back_to_lock(self) -> None:
        """Put the lock back, by request."""
        self._end_study()

    def _end_study(self) -> bool:
        """Tear the strip down and re-assert the lock.

        Returns:
            Whether study mode was running. The strip is always destroyed
            *before* the resume, so a stale tick can never fire against a
            re-grabbed screen.
        """
        session = self._session()
        if not session.active:
            return False
        self._drop_strip()
        outcome = session.resume()
        if not outcome.ok:
            self._say(
                "The lock is back but could not re-take the input grab; it is "
                "retrying every second."
            )
        return True

    def _drop_strip(self) -> None:
        """Destroy the strip if there is one."""
        if self._strip is None:
            return
        self._strip.destroy()
        self._strip = None

    # -- helpers ----------------------------------------------------------

    def _session(self) -> StudySession:
        """The study session, built on first use."""
        if self._study is None:
            self._study = StudySession(
                self._lock,
                self._config,
                on_fail_closed=self._say,
            )
        return self._study

    def _say(self, message: str) -> None:
        """Put one sentence on every surface's status line.

        The same channel ``on_callback_error`` uses: when something goes wrong
        while the lock is up, the screen is the only place the user is looking.
        """
        for view in self._views.values():
            view.status_line.configure(text=message)
