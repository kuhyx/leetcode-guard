"""The tutor's post-mortem reports, read for the status app's Post-mortem tab.

The tutor writes one report per finished unit at
``<tutor>/postmortems/<subject>/<unit>.json``: a signed document whose
``revisions`` each hold the unit's one-shot rates, a row per problem and the
card changes it applied (shape: ``DOCS-postmortem.md``). This module turns the
LATEST revision of each into a compact, JSON-able row for display.

**Display-only.** The signature is not checked: anyone can edit these files,
so nothing that decides, charges or credits may import this module
(``test_display_only_imports.py`` bans it, transitively). A credit still
exists only because LeetCode confirmed an accepted submission.

Tolerant: a missing dir is ``[]`` (no post-mortem yet, a known state); a file
that cannot be read or is not a report is skipped with one warning and the
others still count. ``dry/``, ``failed/``, ``tasks/``, ``lessons.json`` and
``revisions.json`` are the tutor's own working files, never reports. Output
depends only on the files' content (no mtime, no clock), so the per-minute
snapshot push still deduplicates.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard import _tutor_signed
from leetcode_guard._postmortem_rows import (
    FINDING_CAP,
    Row,
    card_chips,
    count,
    objects,
    pair,
    problem_row,
)
from leetcode_guard._read_json import MISSING
from leetcode_guard._tutor_read import read_tutor_json

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["FINDING_CAP", "read_postmortems", "snapshot_postmortems"]

_logger: Final = logging.getLogger(__name__)

KIND: Final = "postmortem_report"
NOT_REPORT_DIRS: Final = frozenset({"dry", "failed", "tasks"})
NOT_REPORT_FILES: Final = frozenset({"lessons.json", "revisions.json"})

MAX_UNITS = 60
"""Units the snapshot carries, newest kept. Read at call time (tests)."""

SNAPSHOT_MAX_BYTES: Final = 32 * 1024
"""The section's budget inside the ~50 KB snapshot. Over it, the oldest
units lose their problem and card detail first; their rates always ship."""


def _report_paths(root: Path) -> list[Path]:
    """Every ``<subject>/<unit>.json`` under ``root``, sorted."""
    return sorted(
        path
        for path in root.glob("*/*.json")
        if path.parent.name not in NOT_REPORT_DIRS and path.name not in NOT_REPORT_FILES
    )


def _latest(doc: object) -> tuple[Row, Row] | None:
    """A report and its highest-``rev`` revision, or ``None`` if not a report."""
    if not isinstance(doc, dict) or doc.get("kind") != KIND:
        return None
    if not isinstance(doc.get("subject"), str) or not isinstance(doc.get("unit"), str):
        return None
    revisions = objects(doc.get("revisions"))
    if not revisions:
        return None
    return doc, max(revisions, key=lambda rev: count(rev.get("rev")) or 0)


def _unit_row(doc: Row, latest: Row) -> Row:
    """The display row of one unit."""
    one_shot = latest.get("one_shot")
    rates = one_shot if isinstance(one_shot, dict) else {}
    return {
        "subject": doc["subject"],
        "unit": doc["unit"],
        "rev": count(latest.get("rev")),
        "at": count(latest.get("at")),
        "post": pair(rates.get("post")),
        "pre": pair(rates.get("pre")),
        "problems": [problem_row(row) for row in objects(latest.get("problems"))],
        "cards": card_chips(latest),
    }


def read_postmortems(root: Path | None = None) -> list[Row]:
    """Every readable report's latest revision, oldest unit first.

    Args:
        root: The tutor's data dir; ``None`` = the configured one.
    """
    base = (_tutor_signed.TUTOR_DIR if root is None else root) / "postmortems"
    rows: list[Row] = []
    for path in _report_paths(base):
        doc = read_tutor_json(path, _logger)
        if doc is MISSING:
            continue
        report = _latest(doc)
        if report is None:
            _logger.warning("skipping %s: not a post-mortem report", path)
            continue
        rows.append(_unit_row(*report))
    rows.sort(key=lambda row: (row["at"] or 0, str(row["subject"]), str(row["unit"])))
    return rows


def _size(rows: list[Row]) -> int:
    return len(json.dumps(rows, sort_keys=True, separators=(",", ":")))


def snapshot_postmortems(max_bytes: int = SNAPSHOT_MAX_BYTES) -> list[Row] | None:
    """The snapshot's ``postmortems`` section, size-capped. Never raises.

    ``None`` means only that reading raised (logged at warning); the app shows
    it as unknown, while ``[]`` is "no post-mortem yet".
    """
    try:
        rows = read_postmortems()[-MAX_UNITS:]
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _logger.warning(
            "post-mortem view failed, section unknown: %s",
            type(exc).__name__,
            exc_info=True,
        )
        return None
    for row in rows:
        if _size(rows) <= max_bytes:
            break
        row["problems"] = None
        row["cards"] = None
    return rows
