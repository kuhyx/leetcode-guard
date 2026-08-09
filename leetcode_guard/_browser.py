"""Open a problem in the user's real browser.

The package could not do this at all until 2026-08-05, which is most of why the
lock was unsatisfiable that morning: it named ten problems it would accept and
offered no way to reach any of them. A gate exists to force the solve, not to
prevent it.

Launching is *not* on its own enough. The production lock holds a global X grab
(``XGrabPointer`` + ``XGrabKeyboard``), and while that is held no other client
receives a keystroke -- a browser started under it comes up unusable, which
would have been the same trap with a button on it. :mod:`leetcode_guard._study`
owns releasing the grab. This module only spawns, and deliberately knows
nothing about locks.

Two decisions worth keeping:

``webbrowser`` is not used. Its ``BROWSER`` handling can select a terminal
browser and run it *in process*, which inside a Tk mainloop under a lock is a
hang with the screen still grabbed. An explicit :func:`subprocess.Popen` of a
resolved absolute path has no such mode.

``start_new_session=True`` is load-bearing, not hygiene. The service unit reaps
its control group, so without a new session ``systemctl --user stop
leetcode-guard.service`` -- the break-glass command printed on the lock itself
-- would kill the browser the user is mid-solve in. Detached, the browser
outlives the lock that opened it.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import shutil
import subprocess
from typing import TYPE_CHECKING, Final, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

_logger: Final = logging.getLogger(__name__)

OPENERS: Final = ("xdg-open", "x-www-browser", "firefox")
"""Tried in order. ``xdg-open`` honours the desktop's own default, which is
what the user expects; the rest are fallbacks for a bare X session."""


class SpawnFn(Protocol):
    """The subset of :class:`subprocess.Popen` this module needs."""

    def __call__(
        self, args: Sequence[str], *, start_new_session: bool
    ) -> object: ...  # pragma: no cover -- structural type only


@dataclass(frozen=True)
class LaunchResult:
    """What came of trying to open a URL."""

    ok: bool
    reason: str
    command: tuple[str, ...] = ()


def find_opener() -> str | None:
    """The absolute path of the first available opener, or ``None``.

    Separate from :func:`launch` so a caller can find out whether a browser
    exists *before* weakening a lock for it. Suspending the grab and only then
    discovering there is nothing to launch would leave the machine unguarded
    for no benefit at all.
    """
    for candidate in OPENERS:
        found = shutil.which(candidate)
        if found is not None:
            return found
    return None


def launch(url: str, *, spawn: SpawnFn | None = None) -> LaunchResult:
    """Open ``url`` in a detached browser process.

    Args:
        url: The full problem URL.
        spawn: Injected for tests, which must never fork. Defaults to
            :class:`subprocess.Popen`.

    Returns:
        The outcome. Never raises: a lock that crashes while trying to be
        helpful is worse than one that says it could not open a browser.
    """
    opener = find_opener()
    if opener is None:
        reason = f"no browser launcher found (tried {', '.join(OPENERS)})"
        _logger.warning("could not open %s: %s", url, reason)
        return LaunchResult(ok=False, reason=reason)

    command = (opener, url)
    launcher = spawn if spawn is not None else subprocess.Popen
    try:
        launcher(command, start_new_session=True)
    except (OSError, ValueError) as exc:
        # OSError: the opener was unlinked between `which` and here, or the
        # process table is full. ValueError: the URL carries an embedded NUL,
        # which `Popen` rejects outright -- reachable because the slug comes
        # from LeetCode's JSON and nothing validates it. That one used to
        # escape, and it escaped *after* the grab was released, so a malformed
        # API response left the machine open. "Never raises" has to be true or
        # it is worse than no promise at all.
        reason = f"{opener} could not be started: {exc}"
        _logger.exception("could not open %s", url)
        return LaunchResult(ok=False, reason=reason, command=command)

    _logger.info("opened %s with %s", url, opener)
    return LaunchResult(ok=True, reason=f"opened with {opener}", command=command)
