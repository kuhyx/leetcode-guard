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

The browser gets its own cgroup: the opener runs under ``systemd-run --user
--scope`` whenever that exists. A browser cold-started from Open otherwise lands
in ``leetcode-guard.service``'s cgroup (2026-11-22: Chrome ran there, peak
2 GB), where the unit's ``MemorySwapMax=0`` would pin it in RAM and ``systemctl
--user stop leetcode-guard.service`` -- the break-glass command printed on the
lock itself -- kills the whole cgroup, the tab the user is solving in included.
``start_new_session=True`` stays as well, so the lock's session ending cannot
signal it either. The tutor's learn window is launched the same way: its
``setsid -f`` leaves the caller's cgroup untouched, so without the scope the
lesson window died with the lock.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import shutil
import subprocess
from typing import TYPE_CHECKING, Final, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

_logger: Final = logging.getLogger(__name__)

OPENERS: Final = ("xdg-open", "x-www-browser", "firefox")
"""Tried in order. ``xdg-open`` honours the desktop's own default, which is
what the user expects; the rest are fallbacks for a bare X session."""

TUTOR: Final = "tutor"
"""The tutor's launcher (SPEC C4): ``tutor --route <route>`` opens its own
Chromium ``--app`` window on that route. Looked up on ``PATH`` first, so a
check can stand a fake in, then in ``~/.local/bin``, which the systemd user
manager's ``PATH`` does not include."""


SCOPE_FLAGS: Final = ("--user", "--scope", "--collect", "--quiet")
"""``systemd-run`` flags for the browser's own transient scope. ``--scope``
runs the opener in place, so the opener still inherits ``DISPLAY``."""


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


def _scope_prefix() -> tuple[str, ...]:
    """``systemd-run`` and its flags, or nothing when it is not installed."""
    runner = shutil.which("systemd-run")
    return () if runner is None else (runner, *SCOPE_FLAGS)


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

    command = (*_scope_prefix(), opener, url)
    return _run_detached(command, opener=opener, what=url, spawn=spawn)


def find_tutor() -> str | None:
    """The tutor launcher's absolute path, or ``None``; spawns nothing.

    Same reason as :func:`find_opener`: the lock asks before it stands down.
    """
    found = shutil.which(TUTOR)
    if found is not None:
        return found
    fallback = Path.home() / ".local" / "bin" / TUTOR
    if fallback.is_file() and os.access(fallback, os.X_OK):
        return str(fallback)
    return None


def launch_tutor(route: str, *, spawn: SpawnFn | None = None) -> LaunchResult:
    """Run ``tutor --route <route>`` detached and scoped. Never raises."""
    tutor = find_tutor()
    if tutor is None:
        reason = f"no {TUTOR} launcher on PATH or in ~/.local/bin"
        _logger.warning("could not open %s: %s", route, reason)
        return LaunchResult(ok=False, reason=reason)
    command = (*_scope_prefix(), tutor, "--route", route)
    return _run_detached(command, opener=tutor, what=route, spawn=spawn)


def _run_detached(
    command: tuple[str, ...], *, opener: str, what: str, spawn: SpawnFn | None
) -> LaunchResult:
    """Spawn ``command`` in a new session; a failure is a result, not a raise."""
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
        _logger.exception("could not open %s", what)
        return LaunchResult(ok=False, reason=reason, command=command)

    _logger.info("opened %s with %s", what, opener)
    return LaunchResult(ok=True, reason=f"opened with {opener}", command=command)
