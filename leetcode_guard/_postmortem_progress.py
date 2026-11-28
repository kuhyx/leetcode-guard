"""The tutor's running post-mortem, read for the status app's progress card.

The tutor writes ``<tutor>/postmortems/progress.json`` at each stage of a
post-mortem (``tutor/postmortem/progress.py``; ``DOCS-postmortem.md``): which
unit, which stage, when it started, how long it should take, and how it ended.
This module shapes it into the snapshot's ``postmortem_progress`` section; the
app computes elapsed time and the ETA itself, so the output holds no clock and
the per-minute push still deduplicates between stage changes.

**Display-only.** The file is unsigned and anyone can edit it, so nothing that
decides, charges or credits may import this module
(``test_display_only_imports.py`` bans it, transitively).

``None`` means no post-mortem has ever reported progress (or the file is
unreadable: warned); a known file always yields every key, ``None`` for a
field that is missing or of the wrong type.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final

from leetcode_guard import _tutor_signed
from leetcode_guard._read_json import MISSING
from leetcode_guard._tutor_read import read_tutor_json

if TYPE_CHECKING:
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)

STATES: Final = frozenset({"running", "done", "failed"})
STAGES: Final = frozenset({"analysing", "applying", "saving"})
SUMMARY_KEYS: Final = ("added", "edited", "untaught", "suspended", "refused")
ERROR_CAP: Final = 200


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if value >= 0 else None


def _pick(value: object, allowed: frozenset[str]) -> str | None:
    return value if isinstance(value, str) and value in allowed else None


def _summary(value: object) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    return {
        key: count
        for key in SUMMARY_KEYS
        if isinstance(count := value.get(key), int) and not isinstance(count, bool)
    }


def _text(value: object, cap: int) -> str | None:
    return value[:cap] if isinstance(value, str) else None


def read_progress(root: Path | None = None) -> dict[str, Any] | None:
    """The shaped progress row, or ``None`` when there is none (or unreadable).

    Args:
        root: The tutor's data dir; ``None`` = the configured one.
    """
    base = _tutor_signed.TUTOR_DIR if root is None else root
    path = base / "postmortems" / "progress.json"
    if not path.exists():
        return None
    doc = read_tutor_json(path, _logger)
    if doc is MISSING:
        return None
    if not isinstance(doc, dict) or _pick(doc.get("state"), STATES) is None:
        _logger.warning("skipping %s: not a post-mortem progress file", path)
        return None
    rev = doc.get("rev")
    return {
        "state": doc["state"],
        "unit": _text(doc.get("unit"), 80),
        "rev": rev if isinstance(rev, int) and not isinstance(rev, bool) else None,
        "stage": _pick(doc.get("stage"), STAGES),
        "started_at": _num(doc.get("started_at")),
        "stage_at": _num(doc.get("stage_at")),
        "finished_at": _num(doc.get("finished_at")),
        "estimate_s": _num(doc.get("estimate_s")),
        "summary": _summary(doc.get("summary")),
        "error": _text(doc.get("error"), ERROR_CAP),
    }


def snapshot_progress() -> dict[str, Any] | None:
    """The snapshot's ``postmortem_progress`` section. Never raises."""
    try:
        return read_progress()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _logger.warning(
            "post-mortem progress failed, section unknown: %s",
            type(exc).__name__,
            exc_info=True,
        )
        return None
