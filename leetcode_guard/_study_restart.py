"""Study mode survives a restart of the lock process.

A restart (``systemctl --user restart leetcode-guard``, a deploy, a crash) used
to end study mode: SIGTERM runs ``on_close``, which re-locks, and the new
process arms fully LOCKED with the grab. kuhy's rule is that restarting changes
nothing, so a lock that was in study mode comes back in study mode.

The memory is one runtime file, ``$XDG_RUNTIME_DIR/leetcode-guard/study.json``
holding the day. It is **never ledger state** and never under
``~/.local/share``: a study flag in the ledger is the same shape as the
deferral that bought unlocked days with ``rm ledger.json`` (``CLAUDE.md``). A
runtime directory is tmpfs, so a reboot or logout clears it by itself.

* Written when study mode has started (the browser launched).
* Cleared when study ends for a real reason: "Back to lock", or a landed solve.
  ``on_close`` (SIGTERM included) winds study down to give the grab and VT
  switching back, and leaves the marker, or a restart could never resume.
* Read by ``_cli._run_lock`` only after ``decide_today`` and after every
  deferral, so only a run that is about to arm a lock ever looks at it.

**Fail closed.** No marker, an unreadable or malformed one, one for another
day, or no ``XDG_RUNTIME_DIR``: the lock comes back LOCKED, and every case but
"no marker" says why at warning. A forged marker gains nothing -- study mode is
one click away at t=0 -- and nothing here decides, charges, credits or settles a
day: it only chooses between two states the lock can already be in.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Protocol

from leetcode_guard._daycost import local_today
from leetcode_guard._gatelock_internals import start_stepback

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import date

    from gatelock import LockWindow

    from leetcode_guard._lock_deps import GuardDeps
    from leetcode_guard._lock_state import RunState
    from leetcode_guard._study import StudySession

_logger: Final = logging.getLogger(__name__)

SUBDIRECTORY: Final = "leetcode-guard"
FILE_NAME: Final = "study.json"


def marker_path() -> Path | None:
    """The marker's path, read from the environment at call time.

    ``None`` when ``XDG_RUNTIME_DIR`` is unset, empty or relative (the XDG spec
    requires an absolute path): there is nowhere safe to remember anything.
    """
    base = os.environ.get("XDG_RUNTIME_DIR", "")
    if not base or not Path(base).is_absolute():
        return None
    return Path(base) / SUBDIRECTORY / FILE_NAME


def write_marker(day: date) -> bool:
    """Record that study mode is running on ``day``.

    Returns:
        Whether it was written. ``False`` costs the restart-resume only: the
        lock itself is unaffected, so the failure is logged, not raised.
    """
    path = marker_path()
    if path is None:
        _logger.warning("no usable XDG_RUNTIME_DIR; a restart will come back locked")
        return False
    tmp = path.with_suffix(".tmp")
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp.write_text(json.dumps({"day": day.isoformat()}), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        _logger.warning("could not write the study marker", exc_info=True)
        return False
    return True


def clear_marker() -> None:
    """Forget that study mode was running. Missing is fine; never raises."""
    path = marker_path()
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        _logger.warning("could not remove the study marker", exc_info=True)


def read_marker(day: date) -> bool:
    """Whether study mode was running on ``day`` when the last process stopped.

    Anything but a well-formed marker for exactly ``day`` is ``False``.
    """
    path = marker_path()
    if path is None:
        _logger.warning("no usable XDG_RUNTIME_DIR; coming back locked")
        return False
    if not path.exists():
        return False  # the ordinary arm: study was not running
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        _logger.warning("unreadable study marker; coming back locked", exc_info=True)
        return False
    if not isinstance(data, dict) or data.get("day") != day.isoformat():
        _logger.warning("study marker is not for %s; coming back locked", day)
        return False
    return True


class _Guard(Protocol):
    """What this module needs from the lock (``LeetcodeGuard``)."""

    deps: GuardDeps
    run_state: RunState
    remembers_study: bool


def remember_study(guard: _Guard) -> None:
    """Study mode has started: leave the marker, for a production morning lock."""
    if guard.remembers_study and not guard.run_state.demo:
        write_marker(local_today(now=guard.deps.moment()))


def forget_study(guard: _Guard) -> None:
    """Study mode ended for a real reason: remove the marker."""
    if guard.remembers_study and not guard.run_state.demo:
        clear_marker()


class _Resumable(Protocol):
    """What :func:`resume_study` and :func:`wind_down_study` need from the lock."""

    lock: Any
    remembers_study: bool
    run_state: RunState

    def enter_study(self, spawn: Callable[[], bool]) -> None:
        """Stand the lock down through the ordinary path."""

    def back_to_lock(self) -> None:
        """Put the lock back."""

    def session(self) -> StudySession:
        """The study session (``active``)."""

    def drop_strip(self) -> None:
        """Destroy the strip."""

    def relock_study(self) -> bool:
        """Re-assert the lock after study mode."""


def arm_input(lock: LockWindow, *, grab: bool) -> None:
    """Arm the lock's input: the grab, or (a resuming restart) no grab at all."""
    if grab:
        lock.grab_input()
    else:
        start_stepback(lock)


def resume_study(guard: _Resumable) -> bool:
    """Enter study mode on a lock that was armed WITHOUT the grab (a restart).

    Goes through the ordinary ``enter_study`` (VT restored, surfaces withdrawn,
    strip up, polling untouched); the "browser" is a no-op that succeeds, the
    one the user was solving in is still open. If study mode cannot be entered
    the lock is armed with the grab after all, so the fallback is LOCKED.

    Returns:
        Whether the lock is now in study mode.
    """
    _logger.warning("study mode was running before this restart; resuming it")
    try:
        guard.enter_study(lambda: True)
    except Exception:  # pylint: disable=broad-exception-caught
        _logger.exception("could not resume study mode; arming the lock")
        guard.back_to_lock()
    if guard.session().active:
        return True
    guard.lock.grab_input()  # never leave a surface up without the grab
    return False


def wind_down_study(guard: _Resumable) -> None:
    """``on_close``: a process leaving while it remembers study re-locks nothing.

    The next start decides what the screen shows (a missing marker fails closed
    to LOCKED there), so no re-lock and no grab on the way out. Otherwise (demo,
    evening, nothing remembered) the old behaviour: put the lock back.
    """
    if guard.session().active and guard.remembers_study and not guard.run_state.demo:
        guard.drop_strip()
        return
    guard.relock_study()
