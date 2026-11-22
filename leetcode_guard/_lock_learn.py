"""The THEORY card's learn button: study mode, then the tutor on the module.

"Enters study mode exactly like Open" (SPEC, Lock screens) is literal: the same
:meth:`~leetcode_guard._lock_study.StudyMixin.enter_study` suspends the grab,
spawns, rolls back on a failed spawn and raises the strip. The tutor is its own
Chromium ``--app`` window, so it needs the grab down for keystrokes exactly as
a browser does -- ``scripts/verify_study_grab.py`` proves both.

The first step is Open's too: **find the launcher before touching the grab.**
A missing ``tutor`` leaves the lock fully asserted, logs a warning and puts
the no-entry glyph on the button (``_view_phase.mark_learn_unavailable``).
Open stays on the same screen, so the lock still offers its way out.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final, Protocol

from leetcode_guard._browser import find_tutor, launch_tutor
from leetcode_guard._launch_watch import watch_exit
from leetcode_guard._view_phase import mark_learn_unavailable
from leetcode_guard._viewmodel_phase import is_review_route, rework_route

if TYPE_CHECKING:
    from collections.abc import Callable

    from leetcode_guard._browser import LaunchResult
    from leetcode_guard._lock_state import RunState
    from leetcode_guard._study import StudySession
    from leetcode_guard._view_group import FrameGroup

_logger: Final = logging.getLogger(__name__)


class LearnHost(Protocol):
    """What the learn button needs from the lock (``StudyMixin``)."""

    frames: FrameGroup
    run_state: RunState
    lock: Any
    fall_open_review: Callable[[], None]

    def enter_study(self, spawn: Callable[[], bool]) -> None:
        """Suspend, spawn, roll back on a failed spawn, raise the strip."""

    def session(self) -> StudySession:
        """The study session (``active``, ``generation``)."""

    def back_to_lock(self) -> None:
        """End study mode for a real reason: forget it, re-assert the lock."""


class LearnButton:
    """What the learn button does; built per press by ``StudyMixin.open_learn``.

    An object rather than a seventh mixin: the lock's ancestor count is
    pylint's limit already.
    """

    def __init__(self, host: LearnHost, say: Callable[[str], None]) -> None:
        """Keep the lock and its status-line reporter."""
        self._host = host
        self._say = say
        self._launch_failed = False
        self._process: object = None

    def open_learn(self, route: str) -> bool:
        """Open the tutor on ``route``, standing the lock down so it can be used.

        Returns:
            ``False`` when the launcher is missing or failed to start (the lock
            is unchanged); the review row falls open on it (``fall_open_review``).
            A launcher that starts and exits non-zero later is :meth:`_exited`.
        """
        if find_tutor() is None:
            _logger.warning(
                "no tutor launcher to open %s with; the lock is unchanged", route
            )
            self._cannot_open("no tutor launcher found")
            return False
        self._host.enter_study(lambda: self._spawn_tutor(route))
        session = self._host.session()
        if not self._launch_failed and session.active:
            generation = session.generation
            watch_exit(
                self._host.lock.root.after,
                self._process,
                lambda status: self._exited(route, status, generation),
            )
        return not self._launch_failed

    def _exited(self, route: str, status: int, generation: int) -> None:
        """The launcher exited ``status`` (non-zero): no window opened.

        Study mode ends the way Back to lock ends it (strip down, grab back,
        restart marker gone), but only when the session this press opened is
        still the one running: after Back to lock, a solve or a later session
        the failure only goes on the status line. A review always falls open.
        """
        _logger.warning("the tutor launcher for %s exited %d", route, status)
        session = self._host.session()
        message = f"the tutor exited {status}"
        if session.active and session.generation == generation:
            self._host.back_to_lock()
            self._cannot_open(message)
        else:
            self._say(message)
        if is_review_route(route):
            self._host.fall_open_review()

    def _spawn_tutor(self, route: str) -> bool:
        """Launch the tutor; guarded like ``_spawn``, since the grab is down."""
        result: LaunchResult | None = None
        try:
            result = launch_tutor(route)
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.exception("the tutor launcher raised; treating as a failure")
        if result is None or not result.ok:
            reason = "it raised" if result is None else result.reason
            self._cannot_open(f"could not open the tutor ({reason})")
            self._launch_failed = True
            return False
        self._process = result.process
        return True

    def _cannot_open(self, message: str) -> None:
        self._say(message)
        views = self._host.frames.views.values()
        mark_learn_unavailable(views, self._host.run_state.config)


def rework_route_for(target: tuple[str, str] | None, slug: str) -> str | None:
    """The rework route for a SOLVE row's ``?``; ``None`` (logged) off SOLVE.

    The target is read at press time, not when the row was built: a press that
    lands after the screen left SOLVE opens nothing and keeps the grab.
    """
    if target is None or not slug:
        _logger.warning("rework %r pressed off SOLVE; ignored", slug)
        return None
    return rework_route(target, slug)
