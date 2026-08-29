"""Put the lock down long enough to actually solve something.

The production lock holds an X *global* grab -- ``XGrabPointer`` plus
``XGrabKeyboard`` -- so while it is up no other client on the display receives a
single keystroke. On 2026-08-05 that met a gate demanding a fresh accepted
submission, and the two together made a lock whose only exit was an action it
had itself made impossible. Adding a button that opens a browser does not fix
that on its own: the browser comes up and silently swallows every key. The grab
has to come down.

So it comes down, deliberately and temporarily. :meth:`StudySession.suspend`
releases the grab and hides the surfaces; :meth:`StudySession.resume` puts both
back. The gate keeps watching for a solve throughout, and a verified submission
still unlocks for real.

**This is the largest deliberate weakening in the package, and it is not
hidden.** Between suspend and resume the machine is genuinely unguarded, with no
timeout -- press Open and walk away and it stays that way. That was chosen
knowingly: a lock that cannot be satisfied is worse than one that can be
walked away from. Both transitions log at warning with elapsed time, so the
journal always says how long the machine was open.

Ordering, in gatelock's own terms
---------------------------------
``RecoveryLoop`` proves that no transition it observes decreases ``G`` (the grab
is held) or ``V`` (VT switching is disabled). We lower both -- but only with the
loop *stopped*, and we restore both before restarting it, so every state the
loop ever sees still satisfies its invariant. The proof is not broken; it is
stepped outside of, with the lights on.

That is also why :meth:`suspend` stops the recovery loop *first* and aborts if
it cannot. A released grab with a live loop is re-taken within one tick
(``recovery_tick_ms``, 1s by default), which would leave a browser that looks
focused and accepts nothing -- the original bug wearing a disguise.

Resume restores each surface itself rather than delegating to
``SurfaceSet.enforce``. ``_enforce_one`` deiconifies and *then* sets
override-redirect, the reverse of the creation path's stated non-negotiable
order, so a surface it revives can come back window-manager-managed and
mis-placed. Restoring in creation order leaves nothing for it to correct.

Private gatelock attributes
---------------------------
``LockWindow._recovery``, ``LockWindow._detector`` and ``SurfaceSet._surfaces``
are private and there is no public equivalent: no public stop for the loop, and
no public accessor for the Toplevels (``infos()`` yields dataclasses,
``names()`` strings). Verified against **gatelock v0.4.0**;
``test_study.py`` asserts all three still exist so a version bump fails at test
time rather than inside a live lock. The clean fix is upstream
``LockWindow.suspend()``/``resume()``, which would serve all four lockers.

``tkinter`` is imported for **one reason**: ``tk.TclError`` is the exception
type every window call here can raise, and catching it by name beats catching
everything. No widget is created and no Tk call is made outside a ``try``, so
every branch below is still reachable from a plain mock -- which is what lets
the ordering be tested without an X server. The import still means this module
belongs in ``_TK_MODULES`` in ``conftest.py``; miss that and the suite opens a
real window or hangs holding a grab.

**A non-Tk exception must never escape a half-finished suspend.** Narrow catches
are the linted, readable choice, but they only cover the failure this code
expects. :meth:`StudySession.suspend` therefore wraps the whole transition, so a
wedged timer raising ``RuntimeError`` mid-way rolls back to a fully asserted
lock instead of leaving the grab released with the state saying locked.
"""

from __future__ import annotations

import logging
import time
import tkinter as tk
from typing import TYPE_CHECKING, Final

from gatelock import disable_vt_switching

from leetcode_guard._gatelock_internals import (
    SuspendableLock,
    mark_vt,
)
from leetcode_guard._study_resume import ResumeMixin
from leetcode_guard._study_steps import SuspendStepsMixin
from leetcode_guard._study_types import StudyState, SuspendOutcome, Withdrawn

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import LockConfig

_logger: Final = logging.getLogger(__name__)


class StudySession(ResumeMixin, SuspendStepsMixin):
    """Suspends and restores one :class:`gatelock.LockWindow`.

    The restore half lives in :class:`~leetcode_guard._study_resume.ResumeMixin`
    -- same 400-line-cap seam ``ReleaseMixin`` uses, and the ordering argument
    for putting the lock back is worth reading in one piece.
    """

    def __init__(
        self,
        lock: SuspendableLock,
        config: LockConfig,
        *,
        on_fail_closed: Callable[[str], None],
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        """Wire a session to a live lock window.

        Args:
            lock: The ``LockWindow``. Its ``root`` and ``surfaces`` are public;
                ``_recovery`` and ``_detector`` are the documented private
                dependency described in the module docstring.
            config: The lock's configuration, read for ``resolved_disable_vt``.
            on_fail_closed: Called with a human sentence when the lock comes
                back degraded -- currently only when the grab cannot be
                re-taken. The caller is expected to put it on screen.
            now: Monotonic clock, injected so elapsed time is testable.
        """
        self._lock = lock
        self._config = config
        self._on_fail_closed = on_fail_closed
        self._now = now
        self._state = StudyState.LOCKED
        self._started: float = 0.0
        self._withdrawn: list[Withdrawn] = []
        self._vt_restored = False

    @property
    def active(self) -> bool:
        """Whether the lock is currently stood down."""
        return self._state is StudyState.STUDYING

    def elapsed_seconds(self) -> float:
        """How long this study session has been running, or ``0.0``."""
        if self._state is StudyState.LOCKED:
            return 0.0
        return self._now() - self._started

    def suspend(self) -> SuspendOutcome:
        """Release the grab and hide the surfaces.

        Returns:
            The outcome. A failure here leaves the lock fully asserted -- the
            caller must not open a browser it cannot type into.
        """
        if self._state is StudyState.STUDYING:
            _logger.warning("study mode is already running; not suspending again")
            return SuspendOutcome(ok=True, reason="already studying")

        steps: list[str] = []
        try:
            return self._suspend(steps)
        except Exception as exc:
            # The steps below catch ``tk.TclError``, which is what window calls
            # actually raise. This is the net under that: anything else -- a
            # wedged timer, a gatelock bug -- must not escape and leave the
            # grab released with the state still saying LOCKED. That half-state
            # is a silently unguarded machine, which is the whole failure mode
            # this module exists to prevent.
            _logger.exception("study mode could not be entered; putting the lock back")
            self._emergency_restore()
            return SuspendOutcome(
                ok=False,
                reason=f"suspend failed unexpectedly: {exc}",
                steps=tuple(steps),
            )

    def _suspend(self, steps: list[str]) -> SuspendOutcome:
        """The transition proper. See :meth:`suspend` for the safety net."""
        stopped = self._stop_watchers(steps)
        if stopped is not None:
            return stopped

        try:
            self._lock.root.grab_release()
        except tk.TclError as exc:
            _logger.exception("could not release the global grab; rolling back")
            return self._rollback_suspend(exc, steps)
        steps.append("grab-released")

        self._restore_vt(steps)
        self._withdraw_surfaces(steps)

        self._state = StudyState.STUDYING
        self._started = self._now()
        _logger.warning(
            "study mode ON: the global grab is released and this machine is "
            "NOT locked until a solve lands or the lock is restored"
        )
        return SuspendOutcome(ok=True, reason="suspended", steps=tuple(steps))

    def resume(self) -> SuspendOutcome:
        """Restore the surfaces, VT lockdown and grab, in that order.

        Returns:
            The outcome. ``ok=False`` means the grab could not be re-taken; the
            surfaces are up regardless, so the screen is never left clear.
        """
        if self._state is StudyState.LOCKED:
            _logger.warning("study mode is not running; nothing to resume")
            return SuspendOutcome(ok=True, reason="not studying")

        elapsed = self.elapsed_seconds()
        steps: list[str] = []
        self._restore_surfaces(steps)
        self._raise_root(steps)

        # Strengthen before grabbing: gatelock disables VT before it draws
        # anything, for the same reason. A failed grab must not also hand back
        # VT switching.
        if self._vt_restored:
            # Store the result the way gatelock does rather than discarding it:
            # `disable_vt_switching` returns False when setxkbmap is missing, and
            # claiming VT is locked down when it is not would be a lie the
            # break-glass text on screen repeats to the user.
            mark_vt(self._lock, disabled=disable_vt_switching())
            self._vt_restored = False
            steps.append("vt-disabled")

        self._state = StudyState.LOCKED
        self._started = 0.0
        regrabbed = self._regrab()
        steps.append("regrab-requested")
        self._start_watchers(steps)
        self._refocus(steps)

        _logger.warning("study mode OFF after %.0fs; the lock is back", elapsed)
        if not regrabbed:
            return SuspendOutcome(
                ok=False, reason="the grab was not re-taken", steps=tuple(steps)
            )
        return SuspendOutcome(ok=True, reason="resumed", steps=tuple(steps))
