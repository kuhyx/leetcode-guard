"""One gate process at a time.

The afternoon retry fires while the morning run may still be waiting its turn
behind the workout lock. Without this, two waiters would queue behind each
other and the user would clear the gate twice. Copied in shape from
``diet_guard._gatelock.acquire_gate_lock``.

Liveness is the kernel's ``flock``, held for the process lifetime: it is
released on *any* death, including SIGKILL and a crashed X server. No PID
files, no staleness heuristics, no timeouts.
"""

from __future__ import annotations

from dataclasses import dataclass
import fcntl
import logging
import os
from typing import IO, TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)


@dataclass
class InstanceLock:
    """A held single-instance lock."""

    handle: IO[str]
    path: Path

    def release(self) -> None:
        """Drop the lock. Idempotent, and safe on a closed handle."""
        try:
            self.handle.close()
        except OSError as exc:
            _logger.warning("could not close the instance lock %s: %s", self.path, exc)


def acquire(path: Path) -> InstanceLock | None:
    """Take the single-instance lock, or ``None`` if another run holds it.

    Opened ``"a+"`` rather than ``"w"``: ``"w"`` truncates at ``open()`` time,
    which happens *before* the lock attempt, so a losing contender would erase
    the incumbent's record on its way out.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+", encoding="utf-8")
    except OSError:
        _logger.exception("cannot open the instance lock %s", path)
        return None
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        _logger.warning(
            "another leetcode-guard run already holds %s -- standing down", path
        )
        handle.close()
        return None
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return InstanceLock(handle=handle, path=path)
