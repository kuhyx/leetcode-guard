"""The individual steps of a suspend, and the emergency undo of one.

Split out of ``_study.py`` for the 250-line cap, along the same seam
``ResumeMixin`` already uses: ``_study.py`` keeps the transition's shape and
its ordering argument, this file holds the steps it is made of.
"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import TYPE_CHECKING, Any, Final

from gatelock import disable_vt_switching, restore_vt_switching

from leetcode_guard._gatelock_internals import (
    mark_vt,
    stop_detector,
    stop_recovery,
    surface_windows,
)
from leetcode_guard._study_types import StudyState, SuspendOutcome, Withdrawn

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import LockConfig

_logger: Final = logging.getLogger(__name__)


class SuspendStepsMixin:
    """The step half of :class:`~leetcode_guard._study.StudySession`.

    Reads ``_lock``, ``_config``, ``_state``, ``_vt_restored`` and
    ``_withdrawn`` from the class it is mixed into, and calls back into
    ``_start_watchers``, ``_restore_surfaces``, ``_raise_root`` and
    ``_regrab``. Declared rather than assumed, as ``ResumeMixin`` does: a mixin
    that silently expects attributes is one that breaks on a refactor and says
    nothing until runtime.
    """

    _lock: Any
    _config: LockConfig
    _state: StudyState
    _vt_restored: bool
    _withdrawn: list[Any]
    _start_watchers: Callable[[list[str]], None]
    _restore_surfaces: Callable[[list[str]], None]
    _raise_root: Callable[[list[str]], None]
    _regrab: Callable[[], bool]

    def _emergency_restore(self) -> None:
        """Put everything back after an unexpected failure mid-suspend.

        Best effort and deliberately unconditional: whatever state the
        transition reached, the lock must end up asserted rather than
        half-released. Each call is independently guarded because any of them
        may be the one that was already broken.
        """
        self._state = StudyState.LOCKED
        self._guarded(self._restore_surfaces_quietly)
        self._guarded(self._regrab_quietly)
        self._start_watchers([])

    @staticmethod
    def _guarded(step: Callable[[], None]) -> None:
        """Run one emergency-restore step, logging whatever it does wrong.

        Broad on purpose, and the only place in this module that is: this runs
        precisely when something already behaved unexpectedly, so the one thing
        it must not do is raise again and abandon the remaining steps.
        """
        try:
            step()
        except Exception:
            _logger.exception("emergency restore step failed")

    def _restore_surfaces_quietly(self) -> None:
        """Bring back anything already withdrawn."""
        self._restore_surfaces([])
        self._raise_root([])
        if self._vt_restored:
            mark_vt(self._lock, disabled=disable_vt_switching())
            self._vt_restored = False

    def _regrab_quietly(self) -> None:
        """Take the grab back, ignoring whether it worked; recovery retries."""
        self._regrab()

    # -- suspend steps ----------------------------------------------------

    def _stop_watchers(self, steps: list[str]) -> SuspendOutcome | None:
        """Stop the recovery loop and the output detector.

        Both, and first. ``_verify`` and ``_drain`` are scheduled
        independently, so a live detector can still push a full ``tick()``
        through even once the verifier is stopped -- and a tick re-takes the
        grab and re-deiconifies everything we are about to hide.

        Returns:
            ``None`` on success, or the outcome to return from
            :meth:`suspend`. Failing here is fatal to the transition: a grab we
            cannot keep released is worse than one we never released.
        """
        for name, stop in (
            ("recovery", stop_recovery),
            ("detector", stop_detector),
        ):
            try:
                stop(self._lock)
            except tk.TclError:
                _logger.exception(
                    "could not stop the %s loop; refusing to enter study mode "
                    "because the grab would be re-taken within a tick",
                    name,
                )
                self._start_watchers([])
                return SuspendOutcome(
                    ok=False,
                    reason=f"the {name} loop could not be stopped",
                    steps=tuple(steps),
                )
            steps.append(f"{name}-stopped")
        return None

    def _rollback_suspend(self, exc: BaseException, steps: list[str]) -> SuspendOutcome:
        """Undo a suspend that failed at the grab.

        Nothing has been hidden yet, so putting the watchers back is the whole
        rollback. The caller has already logged the exception.
        """
        self._start_watchers([])
        return SuspendOutcome(
            ok=False,
            reason=f"the input grab could not be released: {exc}",
            steps=tuple(steps),
        )

    def _restore_vt(self, steps: list[str]) -> None:
        """Re-enable VT switching for the duration of the study session."""
        if not self._config.resolved_disable_vt():
            return
        # Set before the call, not after: if `restore_vt_switching` raises we
        # cannot know which side VT landed on, and assuming "still disabled"
        # would skip the re-disable on the way out and walk away from a lock
        # that thinks it is asserted.
        self._vt_restored = True
        restore_vt_switching()
        # Keep gatelock's own bookkeeping truthful in BOTH directions -- see
        # `mark_vt`. Clearing it here without setting it again on resume is how
        # the machine ends up exiting with VT switching still disabled.
        mark_vt(self._lock, disabled=False)
        steps.append("vt-restored")

    def _withdraw_surfaces(self, steps: list[str]) -> None:
        """Hide every lock surface, remembering how to bring it back.

        Withdraw rather than ``destroy_all`` so the widget tree survives: a
        rebuild would re-fire ``build_surface`` and discard anything half-typed
        into the escape form.
        """
        self._withdrawn = []
        for info, window in surface_windows(self._lock):
            try:
                window.withdraw()
            except tk.TclError:
                # Cosmetic next to the grab, which is already released.
                _logger.warning(
                    "could not withdraw the surface on %s; leaving it up",
                    info.output_name,
                    exc_info=True,
                )
                continue
            self._withdrawn.append(
                Withdrawn(name=info.output_name, window=window, rect=info.rect)
            )
        steps.append(f"surfaces-withdrawn:{len(self._withdrawn)}")

        try:
            self._lock.root.withdraw()
        except tk.TclError:
            _logger.warning("could not withdraw the backdrop root", exc_info=True)
            return
        steps.append("root-withdrawn")
