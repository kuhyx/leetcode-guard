"""The one-minute harvester's display-only ``history:`` line.

kuhy, 2026-11-22: a Claude coaching a problem "should also have access to my
history of approaches", failed and accepted. Each run mirrors ONE slug into
``history/<slug>.json`` (``_history_store``), at most one page of
``questionSubmissionList`` plus ``CODE_BUDGET`` ``submissionDetails`` reads, so
the harvester's minute stays a handful of requests and a rate limit (which
LeetCode answers like an expired session) is never provoked.

Which slug: the problems he touched (attempts.json submissions, ledger credits),
in this order -- one with activity newer than its mirror, newest first; then a
mirror still owing an older page; then one still owing code. Nothing due: no
request at all.

Called by ``_harvest_run.main`` after the attempts line, fenced there like it:
nothing here may stop a credit or change the exit code. Reads the ledger only
through ``load_ledger``, never saves it. Nothing that decides may import this.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Final

from leetcode_guard import _history_queries
from leetcode_guard._attempt_store import load as load_attempts
from leetcode_guard._constants import LEDGER_FILE
from leetcode_guard._history_queries import PAGE_SIZE
from leetcode_guard._history_store import load, save, valid_slug
from leetcode_guard._ledger import CREDIT
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard._settings import build_client

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from leetcode_guard._history_queries import HistoryPage
    from leetcode_guard._history_store import Mirror

    PageFn = Callable[[str, int], HistoryPage | None]
    CodeFn = Callable[[str], str | None]

_logger: Final = logging.getLogger(__name__)

CODE_BUDGET: Final = 5
"""``submissionDetails`` reads per run."""


def _activity(key_file: Path | None) -> dict[str, int]:
    """Slug -> the newest submission he made on it that this machine knows of."""
    newest: dict[str, int] = {}

    def note(slug: object, at: int) -> None:
        if isinstance(slug, str) and valid_slug(slug):
            newest[slug] = max(at, newest.get(slug, 0))

    for record in load_attempts().values():
        for sub in record.submissions.values():
            note(record.slug, sub.at)
    for entry in load_ledger(LEDGER_FILE, key_file=key_file).entries.values():
        raw = entry.detail.get("submitted_at")
        if entry.kind == CREDIT and isinstance(raw, str) and raw.isdigit():
            note(entry.detail.get("title_slug"), int(raw))
    return newest


def _pick(activity: dict[str, int]) -> tuple[Mirror, int | None] | None:
    """The slug due now and the page offset to fetch (``None`` = code only)."""
    later: list[tuple[Mirror, int | None]] = []
    for slug in sorted(activity, key=lambda name: (-activity[name], name)):
        mirror = load(slug)
        if activity[slug] > max(mirror.newest(), mirror.fetched_at):
            return mirror, 0
        if not mirror.complete:
            later.append((mirror, mirror.next_offset))
        elif mirror.missing_code():
            later.append((mirror, None))
    owing_page = [item for item in later if item[1] is not None]
    return (owing_page or later or [None])[0]


def _merge_page(mirror: Mirror, offset: int, page: HistoryPage) -> None:
    """Merge one page and move the backfill cursor."""
    known = set(mirror.rows)
    mirror.merge(page.rows)
    if offset == 0:
        # Over a page of new submissions since the last look: the gap between
        # them and the old mirror is owed again.
        if page.has_next and not known & {row.submission_id for row in page.rows}:
            mirror.complete = False
            mirror.next_offset = max(mirror.next_offset, PAGE_SIZE)
        elif not page.has_next:
            mirror.complete, mirror.next_offset = True, 0
    elif page.has_next:
        mirror.next_offset = offset + PAGE_SIZE
    else:
        mirror.complete, mirror.next_offset = True, 0


def _plural(number: int, noun: str) -> str:
    """``1 submission``, ``2 submissions``."""
    return f"{number} {noun}" + ("" if number == 1 else "s")


def history_line(
    *,
    clock: Callable[[], float] = time.time,
    fetch_page: PageFn | None = None,
    fetch_code: CodeFn | None = None,
    key_file: Path | None = None,
) -> str:
    """Mirror one due slug; describe what happened, for the journal.

    Args:
        clock: Unix seconds; injected so tests never sleep.
        fetch_page: ``(slug, offset) -> page``; ``None`` = the harvester's client.
        fetch_code: ``submission id -> code``; ``None`` = the harvester's client.
        key_file: The ledger's HMAC key override, for tests.

    Returns:
        ``idle``, ``<slug>: could not check``, or
        ``<slug>: 7 submissions, 5 with code``.
    """
    due = _pick(_activity(key_file))
    if due is None:
        return "idle"
    mirror, offset = due
    page_fn, code_fn = _client_fns(fetch_page, fetch_code)
    if offset is not None:
        page = page_fn(mirror.slug, offset)
        if page is None:
            return f"{mirror.slug}: could not check"
        _merge_page(mirror, offset, page)
        mirror.fetched_at = int(clock())
    for sub_id in mirror.missing_code()[:CODE_BUDGET]:
        mirror.set_code(sub_id, code_fn(sub_id))
    save(mirror)
    rows = _plural(len(mirror.rows), "submission")
    return f"{mirror.slug}: {rows}, {mirror.with_code()} with code"


def _client_fns(page: PageFn | None, code: CodeFn | None) -> tuple[PageFn, CodeFn]:
    """The injected fetchers, or both bound to one production client."""
    if page is not None and code is not None:
        return page, code
    post = build_client().post
    return (
        page or (lambda slug, offset: _history_queries.fetch_page(post, slug, offset)),
        code or (lambda sub_id: _history_queries.fetch_code(post, sub_id)),
    )
