"""The tutor's SIGNED files, read for deciding: teaching minutes and module state.

Two files, both rows signed by the tutor with the shared key
(``earned_time.entry_signature``; the same HMAC-SHA256 over the row without
``hmac``, ``sort_keys`` and compact separators that
``gatelock.log_integrity`` verifies):

* ``ledger.json`` (contract C1): minute rows, ``kind`` ``credit`` or (a
  LeetCode subject's, from 2026-11-23) ``leetcode_theory``. A TEACHING turn's
  row carries ``detail.subject`` and ``detail.module``; a REVIEW minute row adds
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


class _Reasons(logging.Logger):
    """A logger that keeps each message in a list and logs nothing.

    For a caller that logs once itself (``_review_due.ReviewWatch``). A
    subclass, not ``getLogger``: a registered logger would be shared, and
    would pile up handlers across reads.
    """

    def __init__(self, into: list[str]) -> None:
        """Append every message to ``into``."""
        super().__init__(f"{__name__}.reasons")
        self._into = into

    def handle(self, record: logging.LogRecord) -> None:
        """Keep the message; no handler, no parent logger sees it."""
        self._into.append(record.getMessage())


def _reporter(reasons: list[str] | None) -> logging.Logger:
    """This module's logger, or (``reasons`` given) one that only collects."""
    return _logger if reasons is None else _Reasons(reasons)


def _verified(row: object, key_file: Path | None, logger: logging.Logger) -> bool:
    """Whether ``row`` is a dict with a valid HMAC; a check that RAISES fails the row.

    A planted ``hmac`` of non-ASCII text makes ``hmac.compare_digest`` raise
    ``TypeError``; such a row is unverified like any forgery, never a crash.
    """
    if not isinstance(row, dict):
        return False
    try:
        return verify_entry_hmac(row, key_file=key_file)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("a signature check raised: row unverified")
        return False


def signed_rows(
    name: str,
    *,
    key_file: Path | None = None,
    strict: bool = False,
    reasons: list[str] | None = None,
) -> list[Row] | None:
    """The verified rows of ``<TUTOR_DIR>/<name>``, or ``None`` if it cannot be read.

    A row whose signature fails (or whose check raises) is dropped, with one
    warning per read; it can never be counted, and dropping it never raises.
    ``strict`` (C2) makes such a row "cannot check" instead: a dropped minutes
    row can only pay less, but a dropped state row can un-do a module, which
    would pay theory again. ``reasons`` (a per-poll reader that logs once itself)
    logs nothing and collects each message there instead.
    """
    path = TUTOR_DIR / name
    log = _reporter(reasons)
    if not key_available(key_file=key_file):
        log.warning("HMAC key unreadable: %s cannot be verified", path)
        return None
    document = read_tutor_json(path, log)
    rows = document.get("entries") if isinstance(document, dict) else None
    if document is MISSING or not isinstance(rows, list):
        log.warning("tutor file %s missing or malformed: cannot check", path)
        return None
    kept = [row for row in rows if _verified(row, key_file, log)]
    if len(kept) != len(rows):
        if strict:
            log.warning(
                "%s: %d unverified rows: cannot check", path, len(rows) - len(kept)
            )
            return None
        log.warning("%s: %d unverified rows ignored", path, len(rows) - len(kept))
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
