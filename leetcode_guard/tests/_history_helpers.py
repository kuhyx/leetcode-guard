"""Scripted LeetCode answers for the ``history:`` line tests (not collected)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from leetcode_guard import _history_store, _history_sync
from leetcode_guard._history_queries import HistoryPage, HistoryRow
from leetcode_guard.tests._attempt_helpers import T0

if TYPE_CHECKING:
    from pathlib import Path


def row(sub_id: int, at: int, status: str = "Wrong Answer") -> HistoryRow:
    """One submission as ``questionSubmissionList`` lists it."""
    return HistoryRow(str(sub_id), status, "python3", at, "40 ms", "17 MB")


class Remote:
    """Scripted pages per offset and code per id; records every call."""

    def __init__(
        self,
        pages: dict[int, HistoryPage | None],
        code: dict[str, str | None] | None = None,
    ) -> None:
        self.pages = pages
        self.code = code
        self.page_calls: list[tuple[str, int]] = []
        self.code_calls: list[str] = []

    def page(self, slug: str, offset: int) -> HistoryPage | None:
        """The scripted page; a missing offset fails the test."""
        self.page_calls.append((slug, offset))
        return self.pages[offset]

    def detail(self, sub_id: str) -> str | None:
        """``code-<id>`` unless scripted otherwise."""
        self.code_calls.append(sub_id)
        return f"code-{sub_id}" if self.code is None else self.code.get(sub_id)


def run(remote: Remote, key: Path, at: float = T0 + 60) -> str:
    """One history run at a fake clock."""
    return _history_sync.history_line(
        clock=lambda: at,
        fetch_page=remote.page,
        fetch_code=remote.detail,
        key_file=key,
    )


def mirror(slug: str) -> dict[str, object]:
    """The mirror file as JSON."""
    loaded: dict[str, object] = json.loads(
        (_history_store.HISTORY_DIR / f"{slug}.json").read_text(encoding="utf-8")
    )
    return loaded


def codes(slug: str) -> dict[str, str | None]:
    """Submission id -> its mirrored code (``None`` when not fetched yet)."""
    rows = mirror(slug)["submissions"]
    assert isinstance(rows, list)
    return {item["id"]: item.get("code") for item in rows}
