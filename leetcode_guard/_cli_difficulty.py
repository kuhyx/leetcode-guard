"""``--backfill-difficulty``: price every credited problem, resumably.

Writes only ``difficulty.json`` (signed rows); never the ledger. Safe to repeat:
a problem with a trusted row is skipped, and ``--max-fetch`` bounds the network
per run so a long backlog finishes over several calls.
"""

from __future__ import annotations

from datetime import datetime

from leetcode_guard._constants import EXIT_OK, LEDGER_FILE
from leetcode_guard._difficulty import credited_slugs, load_weights
from leetcode_guard._difficulty_resolve import resolve_difficulties
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard._settings import build_client


def cmd_backfill_difficulty(*, max_fetch: int) -> int:
    """Resolve missing difficulties for every credited slug and say what is left."""
    now = datetime.now().astimezone()
    slugs = credited_slugs(load_ledger(LEDGER_FILE))
    result = resolve_difficulties(
        slugs,
        post=build_client().post,
        now=now,
        max_fetch=max_fetch,
    )
    table = load_weights()
    unknown = [slug for slug in slugs if table.level(slug) is None]
    print(
        f"difficulty {len(slugs)} credited problems: {result.already} already known, "
        f"{result.resolved} resolved now ({result.fetched} from LeetCode), "
        f"{result.failed} failed, {result.deferred} deferred"
    )
    print(f"unknown    {len(unknown)} (counted as Easy until resolved)")
    return EXIT_OK
