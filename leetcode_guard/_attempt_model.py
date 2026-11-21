"""The on-disk shape of ``attempts.json``: typed records and their (de)coding.

One record per (local day, slug), keyed ``"<day>|<slug>"``::

    {
        "version": 1,
        "records": {
            "2026-11-21|two-sum": {
                "day": "2026-11-21",
                "slug": "two-sum",
                "beats": [[1795287000, "description"]],
                "submissions": {"123": {"status": "Wrong Answer", "at": 1795287100}},
                "theory_at_solve": "done",
            }
        },
    }

Display-only, like every file beside the ledger that anyone can edit: parsing
is tolerant (a bad record is dropped with a warning, the rest survive) and
nothing that decides may import this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any, Final

from leetcode_guard._daycost import local_today

if TYPE_CHECKING:
    from collections.abc import Mapping

_logger: Final = logging.getLogger(__name__)

VERSION: Final = 1
RETENTION_DAYS: Final = 180
_BEAT_FIELDS: Final = 2
"""A beat is ``[unix_seconds, tab]``."""
TABS: Final = ("description", "editorial", "solutions", "submissions")
"""The tabs the browser extension reports."""
THEORY_VALUES: Final = ("none", "done", "pending", "unknown")
"""Mirrors the values of ``_curriculum.Theory``; deliberately not imported."""


@dataclass(frozen=True)
class Beat:
    """One visible-tab heartbeat, stamped by the server's clock."""

    at: int
    tab: str


@dataclass(frozen=True)
class Submission:
    """A LeetCode submission: its ``statusDisplay`` and when it was made."""

    status: str
    at: int


@dataclass
class AttemptRecord:
    """Everything measured for one problem on one local day."""

    day: str
    slug: str
    beats: list[Beat] = field(default_factory=list)
    submissions: dict[str, Submission] = field(default_factory=dict)
    theory_at_solve: str | None = None
    """Absent until set; written once and never overwritten."""


def day_of(timestamp: float) -> str:
    """The local calendar day (ISO) of a unix timestamp.

    Goes through ``_daycost.local_today`` so "day" means exactly what it means
    for the gate's own bookkeeping.
    """
    moment = datetime.fromtimestamp(timestamp, tz=UTC).astimezone()
    return local_today(now=moment).isoformat()


def record_key(day: str, slug: str) -> str:
    """The key of a record inside the document."""
    return f"{day}|{slug}"


def cutoff(today: date) -> str:
    """The oldest day (ISO) a record may have and still be kept."""
    return (today - timedelta(days=RETENTION_DAYS)).isoformat()


def prune(records: dict[str, AttemptRecord], today: date) -> None:
    """Drop records more than :data:`RETENTION_DAYS` before ``today``."""
    floor = cutoff(today)
    for key in [key for key, found in records.items() if found.day < floor]:
        del records[key]


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_day(value: object) -> bool:
    """A canonical ISO date: ``fromisoformat`` alone also accepts ``20261121``."""
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        _logger.warning("attempts.json day %r is not a calendar date", value)
        return False


def _parse_beats(value: object) -> list[Beat] | None:
    if not isinstance(value, list):
        return None
    beats: list[Beat] = []
    for item in value:
        if not (
            isinstance(item, list)
            and len(item) == _BEAT_FIELDS
            and _is_int(item[0])
            and isinstance(item[1], str)
        ):
            return None
        beats.append(Beat(item[0], item[1]))
    return beats


def _parse_submissions(value: object) -> dict[str, Submission] | None:
    if not isinstance(value, dict):
        return None
    found: dict[str, Submission] = {}
    for sub_id, row in value.items():
        if not (
            isinstance(row, dict)
            and isinstance(row.get("status"), str)
            and _is_int(row.get("at"))
        ):
            return None
        found[str(sub_id)] = Submission(row["status"], row["at"])
    return found


def _parse_record(key: str, value: object) -> AttemptRecord | None:
    """One record, or ``None`` when any field is off."""
    if not isinstance(value, dict):
        return None
    day, slug = value.get("day"), value.get("slug")
    beats = _parse_beats(value.get("beats"))
    submissions = _parse_submissions(value.get("submissions"))
    theory = value.get("theory_at_solve")
    if beats is None or submissions is None or not _is_valid_theory(theory):
        return None
    if not (_is_day(day) and isinstance(slug, str)):
        return None
    if key != record_key(str(day), slug):
        return None
    return AttemptRecord(str(day), slug, beats, submissions, theory)


def _is_valid_theory(value: object) -> bool:
    """Absent, or one of :data:`THEORY_VALUES`."""
    return value is None or value in THEORY_VALUES


def parse_document(raw: object) -> dict[str, AttemptRecord] | None:
    """The records of a decoded document, or ``None`` for a wrong top-level shape.

    A single malformed record is dropped with a warning so one bad row cannot
    hide the rest; a wrong version or container is refused as a whole.
    """
    if not isinstance(raw, dict) or raw.get("version") != VERSION:
        _logger.warning("attempts.json has an unexpected shape or version")
        return None
    rows = raw.get("records")
    if not isinstance(rows, dict):
        _logger.warning("attempts.json has no records object")
        return None
    records: dict[str, AttemptRecord] = {}
    for key, value in rows.items():
        parsed = _parse_record(str(key), value)
        if parsed is None:
            _logger.warning("attempts.json record %r is malformed; dropped", key)
        else:
            records[str(key)] = parsed
    return records


def to_document(records: Mapping[str, AttemptRecord]) -> dict[str, Any]:
    """The JSON document for ``records``."""
    return {
        "version": VERSION,
        "records": {key: _encode(found) for key, found in records.items()},
    }


def _encode(found: AttemptRecord) -> dict[str, Any]:
    encoded: dict[str, Any] = {
        "day": found.day,
        "slug": found.slug,
        "beats": [[beat.at, beat.tab] for beat in found.beats],
        "submissions": {
            sub_id: {"status": sub.status, "at": sub.at}
            for sub_id, sub in found.submissions.items()
        },
    }
    if found.theory_at_solve is not None:
        encoded["theory_at_solve"] = found.theory_at_solve
    return encoded
