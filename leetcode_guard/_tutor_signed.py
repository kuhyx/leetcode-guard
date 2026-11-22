"""The tutor's SIGNED files, read for deciding: teaching minutes and module state.

Two files, both rows signed by the tutor with the shared key
(``earned_time.entry_signature``; the same HMAC-SHA256 over the row without
``hmac``, ``sort_keys`` and compact separators that
``gatelock.log_integrity`` verifies):

* ``ledger.json`` (contract C1): credit rows. A TEACHING turn's row carries
  ``detail.subject`` and ``detail.module``; a REVIEW minute row adds
  ``detail.activity == "review"``; drill, leftover, carry and the tutor's old
  review rows carry none of those keys (counting them: ``_tutor_minutes``).
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

import logging
from pathlib import Path
from typing import Final

from gatelock.log_integrity import verify_entry_hmac

from leetcode_guard._ledger import key_available
from leetcode_guard._read_json import MISSING
from leetcode_guard._tutor_read import read_tutor_json

_logger: Final = logging.getLogger(__name__)

TUTOR_DIR = Path.home() / ".local" / "share" / "tutor"
"""Read at call time, so the test suite can point it at a scratch dir."""

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


def detail_of(row: Row) -> dict[str, object]:
    """The row's ``detail`` object, or an empty one."""
    detail = row.get("detail")
    return detail if isinstance(detail, dict) else {}


def _state(row: Row) -> tuple[ModuleKey, float, bool] | None:
    """A ``module_state`` row's key, ``at`` and ``done``, or ``None`` if malformed."""
    detail = detail_of(row)
    subject, module = detail.get("subject"), detail.get("module")
    done, at = detail.get("done"), detail.get("at")
    if row.get("kind") != "module_state" or not isinstance(done, bool):
        return None
    if not isinstance(subject, str) or not isinstance(module, str):
        return None
    if isinstance(at, bool) or not isinstance(at, (int, float)):
        return None
    return (subject, module), float(at), done


def _latest(rows: list[Row]) -> dict[ModuleKey, tuple[float, bool, Row]]:
    """The latest (``at``, ``done``, row) per module; a tie: the later row."""
    latest: dict[ModuleKey, tuple[float, bool, Row]] = {}
    for row in rows:
        state = _state(row)
        if state is None:
            continue
        key, at, done = state
        if key not in latest or at >= latest[key][0]:
            latest[key] = (at, done, row)
    return latest


def module_states(rows: list[Row]) -> dict[ModuleKey, tuple[float, bool]]:
    """The latest (``at``, ``done``) per (subject, module); a tie: the later row."""
    return {key: (at, done) for key, (at, done, _) in _latest(rows).items()}


def done_days(rows: list[Row]) -> dict[ModuleKey, object]:
    """Per module whose latest row says done, that row's ``day`` (as signed).

    The same latest-row rule as :func:`module_states`, so a module that flipped
    back is absent however many times it was done before.
    """
    return {
        key: row.get("day") for key, (_, done, row) in _latest(rows).items() if done
    }


def module_done(rows: list[Row]) -> dict[ModuleKey, bool]:
    """The latest ``done`` per (subject, module)."""
    return {key: done for key, (_, done) in module_states(rows).items()}
