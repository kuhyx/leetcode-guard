"""The tutor's SIGNED files, read for deciding: teaching minutes and module state.

Two files, both rows signed by the tutor with the shared key
(``earned_time.entry_signature``; the same HMAC-SHA256 over the row without
``hmac``, ``sort_keys`` and compact separators that
``gatelock.log_integrity`` verifies):

* ``ledger.json`` (contract C1): credit rows. A TEACHING turn's row carries
  ``detail.subject`` and ``detail.module``; review, drill, leftover and carry
  rows carry no ``module`` and so never count here.
* ``module_state.json`` (contract C2): one row per flip of a module's
  ``done``; the latest verified row per (subject, module) wins.

Trusted because signed: an edited or appended row fails its HMAC and is
skipped. The tutor's UNSIGNED files (``log.jsonl``, ``cards.json``) are never
read here; ``_theory`` reads those, for display only.

"Cannot check" is not "no": a missing, unreadable or malformed file, or an
unreadable key, answers ``None`` (logged), never an empty answer. Rows are
parsed as raw dicts: ``_ledger.from_json`` str-casts ``detail`` values, after
which no tutor signature could ever match.
"""

from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Final

from gatelock.log_integrity import verify_entry_hmac

from leetcode_guard._ledger import key_available
from leetcode_guard._read_json import MISSING
from leetcode_guard._tutor_read import read_tutor_json

if TYPE_CHECKING:
    from collections.abc import Collection
    from datetime import date

_logger: Final = logging.getLogger(__name__)

TUTOR_DIR = Path.home() / ".local" / "share" / "tutor"
"""Read at call time, so the test suite can point it at a scratch dir."""

UNTIL_SLACK_S: Final = 2.0
"""Seconds a teaching row may end after C2's ``at`` and still count as before it.

The tutor stamps the module-state row after the credit row of the turn that
finished the module, so that turn normally ends at or before ``at``. The two
are separate writes; a reorder by a second must not drop the last turn.
``test_theory_last_turn.py`` pins it.
"""

Row = dict[str, object]
ModuleKey = tuple[str, str]


def signed_rows(
    name: str, *, key_file: Path | None = None, strict: bool = False
) -> list[Row] | None:
    """The verified rows of ``<TUTOR_DIR>/<name>``, or ``None`` if it cannot be read.

    A row whose signature fails is dropped, with one warning per read; it can
    never be counted, and dropping it never raises. ``strict`` (C2) makes such
    a row "cannot check" instead: a dropped minutes row can only pay less, but
    a dropped state row can un-do a module, which would pay theory again.
    """
    path = TUTOR_DIR / name
    if not key_available(key_file=key_file):
        _logger.warning("HMAC key unreadable: %s cannot be verified", path)
        return None
    document = read_tutor_json(path, _logger)
    rows = document.get("entries") if isinstance(document, dict) else None
    if document is MISSING or not isinstance(rows, list):
        _logger.warning("tutor file %s missing or malformed: cannot check", path)
        return None
    kept = [
        row
        for row in rows
        if isinstance(row, dict) and verify_entry_hmac(row, key_file=key_file)
    ]
    if len(kept) != len(rows):
        if strict:
            _logger.warning(
                "%s: %d unverified rows: cannot check", path, len(rows) - len(kept)
            )
            return None
        _logger.warning("%s: %d unverified rows ignored", path, len(rows) - len(kept))
    return kept


def _detail(row: Row) -> dict[str, object]:
    """The row's ``detail`` object, or an empty one."""
    detail = row.get("detail")
    return detail if isinstance(detail, dict) else {}


def _state(row: Row) -> tuple[ModuleKey, float, bool] | None:
    """A ``module_state`` row's key, ``at`` and ``done``, or ``None`` if malformed."""
    detail = _detail(row)
    subject, module = detail.get("subject"), detail.get("module")
    done, at = detail.get("done"), detail.get("at")
    if row.get("kind") != "module_state" or not isinstance(done, bool):
        return None
    if not isinstance(subject, str) or not isinstance(module, str):
        return None
    if isinstance(at, bool) or not isinstance(at, (int, float)):
        return None
    return (subject, module), float(at), done


def module_states(rows: list[Row]) -> dict[ModuleKey, tuple[float, bool]]:
    """The latest (``at``, ``done``) per (subject, module); a tie: the later row."""
    latest: dict[ModuleKey, tuple[float, bool]] = {}
    for row in rows:
        state = _state(row)
        if state is None:
            continue
        key, at, done = state
        if key not in latest or at >= latest[key][0]:
            latest[key] = (at, done)
    return latest


def module_done(rows: list[Row]) -> dict[ModuleKey, bool]:
    """The latest ``done`` per (subject, module)."""
    return {key: done for key, (_, done) in module_states(rows).items()}


def _minutes(detail: dict[str, object]) -> int | None:
    """``detail.minutes`` when it is a positive int (never a bool), else ``None``."""
    raw = detail.get("minutes")
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        return None
    return raw


def _ended_on(detail: dict[str, object], day: date, until: float | None) -> bool:
    """Whether ``detail.ended_at`` falls on local ``day`` (and not after ``until``)."""
    raw = detail.get("ended_at")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return False
    if until is not None and raw > until + UNTIL_SLACK_S:
        return False
    return datetime.fromtimestamp(raw).astimezone().date() == day


def teaching_minutes(
    rows: list[Row],
    subject: str,
    modules: Collection[str],
    *,
    day: date,
    until: float | None = None,
) -> int:
    """Signed TEACHING minutes on ``modules`` of ``subject`` that ended on ``day``.

    ``until`` (unix seconds) drops rows that ended later: the minutes taught
    before a unit's theory was done still pay once the machine is in SOLVE,
    the ones after it never do.

    earned_time's tutor rules, copied so both readers pay the same minutes:
    the local day of ``ended_at``, a positive-int ``minutes``, and an
    ``entry_id`` repeated by a replayed write pays once, at its smallest count.
    """
    by_id: dict[object, int] = {}
    anonymous = 0
    for row in rows:
        detail = _detail(row)
        minutes = _minutes(detail)
        if (
            row.get("kind") != "credit"
            or detail.get("subject") != subject
            or detail.get("module") not in modules
            or minutes is None
            or not _ended_on(detail, day, until)
        ):
            continue
        entry_id = row.get("entry_id")
        if entry_id is None:
            anonymous += minutes
        else:
            by_id[entry_id] = min(minutes, by_id.get(entry_id, minutes))
    return anonymous + sum(by_id.values())
