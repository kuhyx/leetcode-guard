"""The snapshot's ``status.lock`` block: the rows the PC lock shows, as data.

The phone's Status tab lists exactly the lock's rows. Both build them through
:func:`~leetcode_guard._viewmodel.lock_rows` over one
:class:`~leetcode_guard._viewmodel_source.ViewSource`, so they cannot drift.
The inputs come from where the lock reads them: the phase from the display-side
unit read (``_status_unit.gather_unit``, the ``view`` passed in), the due cards
from ``_review_due``, the pool from the cache with ``post=None`` (no fetch).

Two gaps remain, both because the snapshot has no LeetCode probe and never
fetches: solved slugs come from the ledger only (the lock also unions the
probe's recent submissions), and the pool is the cached ranking, not the one
the lock live-verified when it opened.

**Display-only**: it imports ``_review_due``, so nothing that decides, charges
or credits may import it (``test_display_only_imports.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from leetcode_guard._browser import find_tutor
from leetcode_guard._ledger_io import solved_slugs
from leetcode_guard._review_due import UNKNOWN, DueStatus, check_due
from leetcode_guard._status import PoolFiles, read_pool
from leetcode_guard._viewmodel import lock_rows
from leetcode_guard._viewmodel_source import ViewSource

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

    from leetcode_guard._ledger_io import Ledger
    from leetcode_guard._phase_view import PhaseView
    from leetcode_guard._review_due import DueRead
    from leetcode_guard._status_model import Verdict


def read_review(
    view: PhaseView, *, at: datetime, key_file: Path | None
) -> DueRead | None:
    """Cards due in the SOLVE unit at ``at``, asked the way the lock asks.

    Mirrors ``_lock_phase.PhaseReader._read_review`` and ``_due_now``: off SOLVE
    or with no module nothing is read, and due cards with no tutor launcher to
    open them are "cannot check", because the lock then shows the SOLVE rows.
    """
    if view.phase != "solve" or not view.review_targets:
        return None
    at_ms = int(at.timestamp() * 1000)
    answer = check_due(view.review_targets, at_ms, key_file=key_file)
    if answer.status is DueStatus.DUE and find_tutor() is None:
        return UNKNOWN
    return answer


def lock_block(verdict: Verdict, source: ViewSource) -> dict[str, Any]:
    """The block for ``source``: the lock's screen and rows, in its order.

    ``unpaid`` is "today still needs credits": a day the balance already covers
    (charged now, the charge not yet written) and a free, sick or not-started
    day are not unpaid.
    """
    screen, lines, _ = lock_rows(source)
    rows: list[dict[str, Any]]
    if screen.review is not None:
        # lock_rows put the one review row in place of the SOLVE rows.
        review = screen.review
        rows = [{"kind": "review", "count": review.count, "route": review.route}]
    else:
        titles = {p.title_slug: p.title for p in source.pool.problems}
        rows = [
            {
                "kind": "problem",
                "title": titles[line.slug],
                "difficulty": line.difficulty,
                "url": line.url,
            }
            for line in lines
        ]
    return {
        "unpaid": verdict.needed > 0 and not verdict.charged_today,
        "unit": screen.unit,
        "phase": screen.phase,
        "learn_route": None if screen.card is None else screen.card.route,
        "rows": rows,
    }


def gather_lock(
    verdict: Verdict,
    view: PhaseView,
    ledger: Ledger,
    *,
    at: datetime,
    key_file: Path | None = None,
) -> dict[str, Any]:
    """Read the pool and the due cards, then build the block. Writes nothing."""
    pool, auth = read_pool(ledger, PoolFiles(), now=at.timestamp())
    source = ViewSource(
        pool,
        auth,
        # Every unsolved problem: the lock's surface scrolls (``_lock_poll``).
        limit=len(pool.problems),
        # The ledger only: the lock also unions its probe's recent submissions,
        # and the snapshot has no probe.
        solved_slugs=solved_slugs(ledger),
        phase=view,
        review=read_review(view, at=at, key_file=key_file),
    )
    return lock_block(verdict, source)
