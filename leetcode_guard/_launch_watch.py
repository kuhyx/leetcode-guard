"""Watch a detached tutor launcher until it exits; report a non-zero exit.

``_browser`` spawns the tutor detached, so on its own the lock never learns the
exit status. A launcher that starts and then fails (the tutor's ``run.sh``
exits 1 when its server never comes up, after a wait of 20 s or more) used to
leave study mode on with nothing to study in: the grab released, no window
(measured on Xvfb, 2026-11-22). ``run.sh`` opens its window last, with
``setsid -f``, so a non-zero exit means no window was opened.

One poll every :data:`WATCH_MS` on the Tk loop (``root.after``): no thread and
no deadline, because the real launcher may take ~100 s to fail, and each poll
reaps the child. Exit 0 ends the watch quietly. A handle without ``poll`` (a
test's stand-in) is not watched. Never raises into the Tk loop.
Still not seen: a launcher that exits 0 on a route the app does not know.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable

    After = Callable[[int, Callable[[], None]], object]  # ``root.after``

_logger: Final = logging.getLogger(__name__)

WATCH_MS: Final = 250
"""How often the exit is polled: a failed launch shows within a quarter second."""


def watch_exit(
    after: After, process: object, on_failure: Callable[[int], None]
) -> bool:
    """Poll ``process`` until it exits; call ``on_failure(status)`` if non-zero.

    Returns:
        Whether a watch was started (``process`` has a ``poll``).
    """
    poll = getattr(process, "poll", None)
    if not callable(poll):
        return False

    def tick() -> None:
        try:
            status = poll()
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.exception("could not poll the tutor launcher; no longer watching")
            return
        if status is None:
            after(WATCH_MS, tick)
        elif isinstance(status, int) and status != 0:
            on_failure(status)

    after(WATCH_MS, tick)
    return True
