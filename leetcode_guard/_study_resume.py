"""Putting the lock back after study mode.

Split from :mod:`leetcode_guard._study` for the repo's 400-line cap, and it is
a real seam: this is the whole "restore the assertion" half, which is the part
whose *ordering* carries the safety argument.

Surfaces first, then VT, then the grab. Each step is a deliberate choice:

* Surfaces come back **before** the grab is attempted, so there is never a
  moment where the screen is clear and the state says locked. A degraded lock
  still looks exactly like a working one.
* VT is re-disabled **before** the grab, gatelock's own idiom -- strengthen
  first, so a grab that fails does not also hand VT switching back.
* Each surface is restored in the *creation-path* order (override-redirect set
  while withdrawn, then geometry, then map), which is why resume never
  delegates to ``SurfaceSet.enforce``: ``_enforce_one`` deiconifies and only
  then sets override-redirect, so a surface it revives can come back
  window-manager-managed and on the wrong monitor.
* The watchers restart **unconditionally**, including after a failed re-grab.
  The recovery loop is the real guarantee -- it re-takes the grab within a tick
  of it becoming free -- so skipping it on failure would make a temporary
  degradation permanent.
"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import TYPE_CHECKING, Any, Final

from leetcode_guard._constants import REGRAB_MAX_ATTEMPTS
from leetcode_guard._gatelock_internals import start_detector, start_recovery

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import LockConfig

    from leetcode_guard._study import _Withdrawn as _WithdrawnSurface

_logger: Final = logging.getLogger(__name__)


class ResumeMixin:
    """The restore half of :class:`~leetcode_guard._study.StudySession`.

    Reads ``_lock``, ``_config``, ``_withdrawn`` and ``_on_fail_closed`` from
    the class it is mixed into. Declared rather than assumed, as
    ``ReleaseMixin`` does: a mixin that silently expects attributes is one that
    breaks on a refactor and says nothing until runtime.
    """

    _lock: Any
    _config: LockConfig
    _withdrawn: list[Any]
    _on_fail_closed: Callable[[str], None]

    def _restore_surfaces(self, steps: list[str]) -> None:
        """Bring each surface back in the creation-path order.

        Override-redirect goes on **while the window is still withdrawn**: set
        after mapping it is ignored, and the surface returns WM-managed and
        placed wherever the window manager likes -- on the wrong monitor, on a
        two-output desk.
        """
        for item in self._withdrawn:
            self._restore_one(item)
        steps.append(f"surfaces-restored:{len(self._withdrawn)}")
        self._withdrawn = []

    def _restore_one(self, item: _WithdrawnSurface) -> None:
        """Bring one surface back, in the creation-path order.

        A surface that will not come back is logged and skipped: the others
        still have to be restored, and stopping here would leave part of the
        screen clear while the state says locked.
        """
        try:
            item.window.overrideredirect(boolean=True)
            item.window.geometry(item.rect.geometry())
            item.window.deiconify()
            item.window.lift()
        except tk.TclError:
            _logger.warning(
                "could not restore the surface on %s", item.name, exc_info=True
            )

    def _raise_root(self, steps: list[str]) -> None:
        """Map the backdrop root again.

        X refuses to grab for a withdrawn window, so this has to succeed before
        the re-grab is worth attempting -- and ``update_idletasks`` is what makes
        the mapping take effect rather than sit in the queue behind us.
        """
        try:
            self._lock.root.deiconify()
            self._lock.root.update_idletasks()
        except tk.TclError:
            # Not fatal here: the re-grab below is what actually matters, and
            # its own failure path is the one that reports.
            _logger.warning("could not re-map the backdrop root", exc_info=True)
            return
        steps.append("root-mapped")

    def _regrab(self) -> bool:
        """Re-take the global grab, retrying a bounded number of times.

        The attempts are **immediate** -- eight calls inside a millisecond,
        not spread over time. This runs from the "Back to lock" button
        callback, so sleeping between tries would freeze the surface for the
        duration and make a lock the user just asked for look hung. Blocking
        the Tk loop to look patient is the wrong trade.

        Which means these attempts only catch a grab that is *already* free.
        That is fine, because they were never the guarantee:
        :meth:`_start_watchers` restarts gatelock's recovery loop
        unconditionally, and it re-takes the grab within a tick
        (``recovery_tick_ms``, 1s) of it becoming available -- including the
        realistic case where the browser is still holding one it is about to
        drop.

        Returns:
            Whether the grab is held. ``False`` is a *degraded* lock, not an
            open one: the surfaces are already back up and VT is already
            re-disabled, and the recovery loop heals the rest.
        """
        if self._config.resolved_grab() != "global":
            return True
        for _attempt in range(REGRAB_MAX_ATTEMPTS):
            if self._try_grab():
                return True
        # Every attempt failed. Degraded, not open: the surfaces are already
        # back up and VT is already re-disabled, and the recovery loop --
        # restarted regardless -- keeps trying every tick.
        _logger.error(
            "could not re-take the global grab after %d attempts; the lock is "
            "showing but not holding input. The recovery loop will keep "
            "retrying every tick.",
            REGRAB_MAX_ATTEMPTS,
        )
        self._on_fail_closed("the input grab could not be re-taken")
        return False

    def _try_grab(self) -> bool:
        """One attempt at the global grab.

        The realistic reason this fails is the browser we just launched holding
        a grab of its own, which it will drop.
        """
        try:
            self._lock.root.focus_force()
            self._lock.root.grab_set_global()
        except tk.TclError:
            _logger.warning("the global grab is not available yet", exc_info=True)
            return False
        return True

    def _start_watchers(self, steps: list[str]) -> None:
        """Restart the detector and the recovery loop.

        Unconditional, including after a failed re-grab: the loop is what
        eventually heals a grab we could not take, so skipping it on failure
        would make the degraded state permanent.
        """
        for name, start in (
            ("detector", start_detector),
            ("recovery", start_recovery),
        ):
            try:
                start(self._lock)
            except tk.TclError:
                _logger.exception("could not restart the %s loop", name)
                continue
            steps.append(f"{name}-started")

    def _refocus(self, steps: list[str]) -> None:
        """Give a surface keyboard focus again.

        gatelock's ``on_focus_ready`` is a one-shot latch with no reset, so it
        will never fire a second time and the app has to do this itself.
        """
        try:
            surfaces = self._lock.surfaces
            surfaces.focus_surface(surfaces.preferred_focus_index())
        except tk.TclError:
            _logger.warning("could not re-focus a surface", exc_info=True)
            return
        steps.append("refocused")
