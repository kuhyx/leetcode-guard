"""``history/<slug>.json``: the mirrored submissions of one problem.

Display-only, like ``attempts.json``: a coaching Claude (the tutor's rework
chat, the ``/leetcode`` coach, lesson generation) reads it as context; nothing
that decides, charges or credits may (``test_display_only_imports``). Read the
directory as ``_history_store.HISTORY_DIR`` (never ``from ... import``): the
test fixture rebinds it.

Shape (one file per slug, newest submission first)::

    {
        "slug": "two-sum",
        "fetched_at": 1795287060,
        "complete": true,
        "next_offset": 0,
        "submissions": [
            {
                "id": "2",
                "status": "Accepted",
                "lang": "python3",
                "timestamp": 1795287000,
                "runtime": "40 ms",
                "memory": "17 MB",
                "code": "...",
            }
        ],
    }

``code`` is absent until fetched. ``complete`` turns true once the oldest page
(``hasNext`` false) has been merged; ``next_offset`` is the page still owed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from typing import TYPE_CHECKING, Final

from leetcode_guard import _constants
from leetcode_guard._atomic_json import write_json
from leetcode_guard._read_json import MISSING, read_json

if TYPE_CHECKING:
    from pathlib import Path

    from leetcode_guard._history_queries import HistoryRow

_logger: Final = logging.getLogger(__name__)

HISTORY_DIR: Final = _constants.DATA_DIR / "history"
CODE_TRIES: Final = 3
"""A submission whose code failed this many reads is not asked for again."""
_SLUG: Final = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def valid_slug(slug: str) -> bool:
    """Whether ``slug`` can name a file (attempts.json is editable: no ``../x``)."""
    return _SLUG.fullmatch(slug) is not None


@dataclass
class Mirror:
    """One problem's mirrored submissions, keyed by submission id."""

    slug: str
    fetched_at: int = 0
    complete: bool = False
    next_offset: int = 0
    rows: dict[str, dict[str, object]] = field(default_factory=dict)

    def newest(self) -> int:
        """The newest mirrored submission's Unix seconds; 0 when none."""
        return max((_stamp(item) for item in self.rows.values()), default=0)

    def missing_code(self) -> list[str]:
        """Ids still lacking code, newest first."""
        order = sorted(self.rows.values(), key=_stamp, reverse=True)
        return [
            str(item["id"])
            for item in order
            if "code" not in item and _tries(item) < CODE_TRIES
        ]

    def set_code(self, sub_id: str, code: str | None) -> None:
        """Store the code, or count one more failed read of it."""
        item = self.rows[sub_id]
        if code is None:
            item["code_tries"] = _tries(item) + 1
        else:
            item["code"] = code
            item.pop("code_tries", None)

    def with_code(self) -> int:
        """How many rows hold their code."""
        return sum("code" in item for item in self.rows.values())

    def merge(self, rows: tuple[HistoryRow, ...]) -> None:
        """Add or refresh rows; a stored ``code`` survives the refresh."""
        for got in rows:
            item = self.rows.setdefault(got.submission_id, {"id": got.submission_id})
            item.update(
                status=got.status,
                lang=got.lang,
                timestamp=got.at,
                runtime=got.runtime,
                memory=got.memory,
            )


def _tries(item: dict[str, object]) -> int:
    """Failed code reads so far."""
    value = item.get("code_tries")
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _stamp(item: dict[str, object]) -> int:
    """A row's timestamp; 0 when off."""
    value = item.get("timestamp")
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def path_of(slug: str) -> Path:
    """Where the slug's mirror lives."""
    return HISTORY_DIR / f"{slug}.json"


def load(slug: str) -> Mirror:
    """The slug's mirror; an empty one when absent or unreadable."""
    raw = read_json(path_of(slug), _logger, "history for %s is unreadable: %s", slug)
    if raw is MISSING:
        return Mirror(slug)
    if not isinstance(raw, dict) or not isinstance(raw.get("submissions"), list):
        _logger.warning("history for %s is unreadable; starting it again", slug)
        return Mirror(slug)
    rows = {
        str(item["id"]): item
        for item in raw["submissions"]
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    offset = raw.get("next_offset")
    return Mirror(
        slug,
        fetched_at=_stamp({"timestamp": raw.get("fetched_at")}),
        complete=raw.get("complete") is True,
        next_offset=offset if isinstance(offset, int) and offset > 0 else 0,
        rows=rows,
    )


def save(mirror: Mirror) -> None:
    """Write the mirror atomically, newest submission first."""
    write_json(
        path_of(mirror.slug),
        {
            "slug": mirror.slug,
            "fetched_at": mirror.fetched_at,
            "complete": mirror.complete,
            "next_offset": mirror.next_offset,
            "submissions": sorted(mirror.rows.values(), key=_stamp, reverse=True),
        },
        indent=1,
    )
