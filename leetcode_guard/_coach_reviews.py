"""Which flagged solves the coach has reviewed: the ``cleared`` set of the report.

The coach (0.1.6, ``/leetcode review``) appends a ``review`` event to the
problem's session log, ``<date>-<slug>.jsonl`` in the folder ``_coach_log``
reads, once kuhy has named exactly one cause. Only that clears a flag: a
``review`` whose ``cause`` is missing or not one of :data:`CAUSES` is an
unfinished review and clears nothing. ``module`` (the curriculum unit, for
``missing-idea``) is payload for the coach, never part of the rule.

Display-only, like the report it feeds: the log is plain unsigned JSONL that
anyone can edit, so **nothing that decides, charges or credits may import
this** (``test_display_only_imports``). Editing the log can only hide a row of
a review list. Standard library only on purpose: it runs inside the MCP
server's venv, which must not need the coach package (so ``_coach_log``, which
imports it, is not used here; the event names are copied and a test ties the
copies to ``_coach_log.EVENTS``).

"Cannot check" is not "reviewed": a folder that cannot be listed logs a
warning and clears nothing, so every flag stays. A missing folder is the known
"no reviews yet". An unreadable file or a torn line is skipped with a warning.
Nothing here raises into ``--flagged`` or ``get_flagged``.
"""

from __future__ import annotations

from datetime import date
import json
import logging
from pathlib import Path
import re
from typing import Final

_logger: Final = logging.getLogger(__name__)

COACH_SESSIONS_DIR = Path.home() / ".local" / "share" / "leetcode-coach" / "sessions"
"""Read at call time, never bound as a default argument, so the test suite can
point it away from the real log (``_paths_fixture``)."""

REVIEW: Final = "review"
SKELETON: Final = "skeleton"
CAUSES: Final = frozenset(
    {"statement", "missing-idea", "idea-to-code", "debugging", "interruption"}
)

_DATED_NAME: Final = re.compile(r"(?P<day>\d{4}-\d{2}-\d{2})-(?P<slug>.+)")


def _slug(stem: str) -> str:
    """``2026-10-23-missing-number`` -> ``missing-number``; undated stays whole."""
    match = _DATED_NAME.fullmatch(stem)
    if match is None:
        return stem
    try:
        date.fromisoformat(match["day"])
    except ValueError as exc:
        _logger.warning("coach session %r: not a date, read as undated: %s", stem, exc)
        return stem
    return match["slug"]


def _finished_review(event: object) -> bool:
    """A ``review`` event naming one of the five causes."""
    if not isinstance(event, dict) or event.get("event") != REVIEW:
        return False
    cause = event.get("cause")
    return isinstance(cause, str) and cause in CAUSES


def _reviewed(path: Path) -> bool:
    """Whether one session file holds a finished review; unreadable is ``False``."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        _logger.warning("coach session %s is unreadable: %s", path, exc)
        return False
    found = False
    for number, line in enumerate(lines, start=1):
        try:
            event = json.loads(line) if line.strip() else None
        except ValueError as exc:
            _logger.warning("%s line %d is not JSON: %s", path, number, exc)
            continue
        found = found or _finished_review(event)
    return found


def reviewed_slugs(directory: Path | None = None) -> frozenset[str]:
    """The slugs with a finished review in the coach log; empty if unknown."""
    folder = COACH_SESSIONS_DIR if directory is None else directory
    if not folder.exists():
        return frozenset()
    try:
        paths = sorted(folder.iterdir())
    except OSError as exc:
        _logger.warning("coach reviews could not check %s: %s", folder, exc)
        return frozenset()
    return frozenset(
        _slug(path.stem)
        for path in paths
        if path.suffix == ".jsonl" and _reviewed(path)
    )
