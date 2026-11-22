"""The lock's X-server probe: same question as gatelock's, without the flood.

2026-11-22 09:00-10:09 the timer's run waited 70 minutes on an X server that
refused its cookie, and the journal took "Authorization required, but no
authorization protocol specified" 8378 times. libX11 prints that itself, to
fd 2, inside ``tk.Tk()``, twice per one-second attempt; no Python log call is
involved, so neither a logging filter nor ``sys.stderr`` can catch it.

So each attempt runs with fd 2 pointed at a scratch file and put back in a
``finally``. The first refusal's text is logged once, at warning, so the
journal still says *why* the lock is not up; after that the only lines are
gatelock's own heartbeat, every ``X_WAIT_HEARTBEAT_S`` (300 s). The wait
itself is unchanged and stays unbounded (CLAUDE.md: never bound the X wait).

The redirect is process-wide while it lasts. It only runs before the lock
exists, and lasts as long as one failed connect, so the worst it can swallow
is another thread's stderr for those milliseconds.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import logging
import os
import tempfile
import tkinter as tk
from typing import IO, TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterator

_logger: Final = logging.getLogger(__name__)
_STDERR_FD: Final = 2
_MAX_KEPT_CHARS: Final = 500


@dataclass
class QuietXProbe:
    """``probe=`` for ``gatelock.wait_for_x_server``; logs one refusal only."""

    reported: bool = field(default=False)

    def __call__(self) -> bool:
        """Whether a throwaway Tk root can be created and destroyed."""
        with tempfile.TemporaryFile() as sink:
            try:
                with _stderr_into(sink):
                    root = tk.Tk()
            except tk.TclError as exc:
                # fd 2 is back by now, so this line reaches the journal.
                if not self.reported:
                    self.reported = True
                    _logger.warning(
                        "X server refused the lock (%s): %s -- waiting; logged "
                        "once, then gatelock's heartbeat every few minutes",
                        exc,
                        _read(sink) or "no message",
                    )
                return False
        root.destroy()
        return True


@contextmanager
def _stderr_into(sink: IO[bytes]) -> Iterator[None]:
    """Point fd 2 at ``sink`` for the block; always put it back."""
    saved = os.dup(_STDERR_FD)
    try:
        os.dup2(sink.fileno(), _STDERR_FD)
        yield
    finally:
        os.dup2(saved, _STDERR_FD)
        os.close(saved)


def _read(sink: IO[bytes]) -> str:
    """What libX11 said, on one journal line (it repeats itself per attempt)."""
    sink.seek(0)
    lines = sink.read().decode(errors="replace").splitlines()
    said = " | ".join(dict.fromkeys(line.strip() for line in lines if line.strip()))
    return said[:_MAX_KEPT_CHARS]
