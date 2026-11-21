"""Bounded, fail-open reads of the tutor app's files.

The tutor is a separate live server, so what is on disk at read time is not
ours to trust: a log cut mid-append, a file replaced by a FIFO, a runaway
log. Every refusal here is a logged WARNING and a ``None``/``MISSING`` answer,
never an exception: this runs while the instance lock is held and before the
lock window opens, so a raise would mean a lock that never arms.

A file is ``stat``-ed before it is opened. Only a regular file under
:data:`MAX_TUTOR_FILE_BYTES` is opened, and then with ``O_NONBLOCK``, so a
FIFO swapped in between the two calls fails with ``EAGAIN`` instead of
blocking.
"""

from __future__ import annotations

import json
import os
import stat
from typing import TYPE_CHECKING, Final

from leetcode_guard._read_json import MISSING

if TYPE_CHECKING:
    import logging
    from pathlib import Path

MAX_TUTOR_FILE_BYTES: Final = 32 * 1024 * 1024
"""Per-file read cap: ~180x the real log (181 KB on 2026-11-21), small enough
that a planted or runaway file cannot cost the arming run gigabytes."""


def _nonblocking(path: str, flags: int) -> int:
    """``open``'s opener: never block on a writer-less FIFO."""
    return os.open(path, flags | os.O_NONBLOCK)


def read_tutor_bytes(path: Path, logger: logging.Logger) -> bytes | None:
    """The bytes of a regular file within the cap, else ``None`` (warned once)."""
    try:
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            logger.warning("tutor file %s is not a regular file, theory unknown", path)
            return None
        if info.st_size > MAX_TUTOR_FILE_BYTES:
            logger.warning("tutor file %s is larger than the cap, theory unknown", path)
            return None
        with open(path, "rb", opener=_nonblocking) as handle:
            data = handle.read(MAX_TUTOR_FILE_BYTES + 1)
    except OSError as exc:
        logger.warning("tutor file %s unreadable, theory unknown: %s", path, exc)
        return None
    if len(data) > MAX_TUTOR_FILE_BYTES:
        logger.warning("tutor file %s outgrew the cap while read, theory unknown", path)
        return None
    return data


def read_tutor_json(path: Path, logger: logging.Logger) -> object:
    """The parsed JSON of a tutor file, or :data:`MISSING` (warned) for any failure."""
    data = read_tutor_bytes(path, logger)
    if data is None:
        return MISSING
    try:
        return json.loads(data.decode("utf-8"))
    except (ValueError, RecursionError) as exc:
        logger.warning("tutor file %s is not valid JSON, theory unknown: %s", path, exc)
        return MISSING
