"""The locked read-modify-write behind every ``attempts.json`` writer.

Split from :mod:`leetcode_guard._attempt_store` for the file-length cap. See
that module for the failure modes this implements: a lock not obtained within
two seconds skips the write, a corrupt file is set aside and replaced, and an
``OSError`` on write is reported as failed -- each logged at warning, none
raised into the caller.
"""

from __future__ import annotations

from datetime import date
import enum
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard import _attempt_paths
from leetcode_guard._atomic_json import write_json
from leetcode_guard._attempt_lock import LockTiming, exclusive
from leetcode_guard._attempt_model import (
    AttemptRecord,
    day_of,
    parse_document,
    prune,
    to_document,
)
from leetcode_guard._read_json import MISSING, read_json

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)

DEFAULT_TIMING: Final = LockTiming()

type Records = dict[str, AttemptRecord]
type Mutation = Callable[[Records, date], int]


class Outcome(enum.Enum):
    """What a write did."""

    WRITTEN = "written"
    SKIPPED = "skipped"
    """Nothing to change (a duplicate beat, a known submission)."""
    FAILED = "failed"
    """Lock, parse-aside or write problem; already logged at warning."""


def resolve_path(path: Path | None) -> Path:
    """The caller's path, or the configured file read at call time."""
    return _attempt_paths.ATTEMPTS_FILE if path is None else path


def load(path: Path | None = None) -> Records:
    """Every record, read-only and tolerant.

    A missing file is empty. An unreadable or wrong-shape file is empty plus a
    warning. Reads never rename or write: only a writer sets a bad file aside.
    """
    raw = read_json(
        resolve_path(path),
        _logger,
        "attempts.json %s is unreadable: %s",
        resolve_path(path),
    )
    if raw is MISSING:
        return {}
    return parse_document(raw) or {}


def _set_aside(path: Path) -> None:
    """Move a corrupt file to ``<name>.corrupt``, replacing an older aside."""
    aside = path.with_name(path.name + ".corrupt")
    _logger.warning("attempts.json %s is corrupt; moving it to %s", path, aside)
    try:
        path.replace(aside)
    except OSError:
        _logger.warning(
            "could not set %s aside; it will be overwritten", path, exc_info=True
        )


def _read_for_write(path: Path) -> Records:
    """The current records, setting a corrupt file aside first."""
    raw = read_json(path, _logger, "attempts.json %s is unreadable: %s", path)
    if raw is MISSING and not path.exists():
        return {}
    records = None if raw is MISSING else parse_document(raw)
    if records is None:
        _set_aside(path)
        return {}
    return records


def update(
    mutate: Mutation, *, now: float, path: Path | None, timing: LockTiming
) -> tuple[Outcome, int]:
    """Lock, read, ``mutate``, prune and write; the heart of every writer.

    Args:
        mutate: Edits the records in place and returns how many things changed.
        now: The server's clock; fixes "today" for retention.
        path: The file, or ``None`` for the configured one.
        timing: Lock timeout and clock.

    Returns:
        The outcome and the change count (0 unless written).
    """
    target = resolve_path(path)
    today = date.fromisoformat(day_of(now))
    with exclusive(target.with_name(target.name + ".lock"), timing) as held:
        if not held:
            return Outcome.FAILED, 0
        records = _read_for_write(target)
        changed = mutate(records, today)
        if changed == 0:
            return Outcome.SKIPPED, 0
        prune(records, today)
        try:
            write_json(target, to_document(records))
        except OSError:
            _logger.warning("could not write %s", target, exc_info=True)
            return Outcome.FAILED, 0
    return Outcome.WRITTEN, changed
