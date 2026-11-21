"""The exclusive lock around ``attempts.json``'s read-modify-write.

Two processes write the file (the status service appends beats, the one-minute
harvester adds submissions), so a plain atomic rename is not enough: both would
read the old document and the second rename would erase the first's change.
``flock`` on a sibling file serialises them; the kernel drops the lock when the
process dies, so a crash cannot leave it held.

Failing to get the lock is a skipped write, never a stall: this is measurement,
and the caller is either a web request or a harvest tick that must finish.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import logging
import os
import time
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)


@dataclass(frozen=True)
class LockTiming:
    """How long to wait for the lock, with the clock and sleep injectable.

    Tests pass fakes so the two-second timeout is never really waited out.
    """

    timeout: float = 2.0
    interval: float = 0.05
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.monotonic


def _acquire(descriptor: int, timing: LockTiming) -> bool:
    """Poll a non-blocking ``flock`` until it is taken or the deadline passes."""
    deadline = timing.monotonic() + timing.timeout
    while True:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if timing.monotonic() >= deadline:
                _logger.warning(
                    "attempts.json lock not obtained within %.1fs; skipping the write",
                    timing.timeout,
                )
                return False
            timing.sleep(timing.interval)
        else:
            return True


@contextmanager
def exclusive(lock_path: Path, timing: LockTiming) -> Iterator[bool]:
    """Hold the lock for the ``with`` body; yields whether it was obtained.

    Fail-open, logged at warning: a lock file that cannot be created or taken
    yields ``False`` instead of raising, and the caller skips its write.
    """
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        _logger.warning(
            "cannot open the attempts.json lock file %s; skipping the write",
            lock_path,
            exc_info=True,
        )
        yield False
        return
    try:
        yield _acquire(descriptor, timing)
    finally:
        os.close(descriptor)
