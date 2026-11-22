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
from typing import TYPE_CHECKING, Final

from leetcode_guard._browser import find_tutor, launch_tutor
from leetcode_guard._view_phase import mark_learn_unavailable

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import LockConfig

    from leetcode_guard._browser import LaunchResult
    from leetcode_guard._view_group import FrameGroup

_logger: Final = logging.getLogger(__name__)


class LearnButton:
    """What the learn button does; built per press by ``StudyMixin.open_learn``.

    An object rather than a seventh mixin: the lock's ancestor count is
    pylint's limit already. It gets the two study-mode calls it needs.
    """

    def __init__(
        self,
        enter_study: Callable[[Callable[[], bool]], None],
        say: Callable[[str], None],
        frames: FrameGroup,
        config: LockConfig,
    ) -> None:
        """Keep the study entry, the status-line reporter and the surfaces."""
        self._enter_study = enter_study
        self._say = say
        self._frames = frames
        self._config = config

    def open_learn(self, route: str) -> None:
        """Open the tutor on ``route``, standing the lock down so it can be used."""
        if find_tutor() is None:
            _logger.warning(
                "no tutor launcher to open %s with; the lock is unchanged", route
            )
            self._cannot_open("no tutor launcher found")
            return
        self._enter_study(lambda: self._spawn_tutor(route))

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
            return False
        return True

    def _cannot_open(self, message: str) -> None:
        self._say(message)
        mark_learn_unavailable(self._frames.views.values(), self._config)
