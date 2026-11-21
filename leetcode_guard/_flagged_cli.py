"""``--flagged``: solves that took long although their theory was taught.

Read-only over the ledger, ``attempts.json`` and the coach log; prints and
writes nothing else. Lives outside the ``_cli*`` names on purpose: those modules are the
windows' neighbours and may not import display-only readers directly
(``test_display_only_imports``); this one is a terminal diagnostic that reads
them by design.
"""

from __future__ import annotations

import json
from typing import Any

from leetcode_guard._attempt_report import load_report
from leetcode_guard._coach_reviews import reviewed_slugs
from leetcode_guard._constants import EXIT_OK

_SECONDS_PER_MINUTE = 60


def _minutes(seconds: int) -> str:
    return f"{round(seconds / _SECONDS_PER_MINUTE)}m"


def flagged_line(row: dict[str, Any]) -> str:
    """One flagged solve: the evidence a review starts from."""
    span = "n/a" if row["span_seconds"] is None else _minutes(row["span_seconds"])
    failed = ", ".join(f"{count} {kind}" for kind, count in row["failed"].items())
    tabs = " ".join(f"{tab} {_minutes(sec)}" for tab, sec in row["tab_seconds"].items())
    return (
        f"{row['slug']}  active {_minutes(row['active_seconds'])}  span {span}"
        f"  failed {failed or 'none'}"
        f"  first submit {_minutes(row['first_submission_active_seconds'])}"
        f"  tabs {tabs}"
    )


def summary_line(report: dict[str, Any]) -> str:
    """Counts and the share of fast solves; ``n/a`` when nothing was measured."""
    share = report["under_10_min_share"]
    shown = "n/a" if share is None else f"{share:.0%}"
    return (
        f"measured {len(report['measured'])}, unknown {len(report['unknown'])}, "
        f"under 10 min {shown}"
    )


def cmd_flagged(*, as_json: bool) -> int:
    """Print the flagged solves and a summary, or the whole report as JSON.

    A solve the coach has reviewed (``_coach_reviews``) is not flagged.
    """
    report = load_report(cleared=reviewed_slugs())
    if as_json:
        print(json.dumps(report, sort_keys=True, indent=2))
        return EXIT_OK
    for row in report["flagged"]:
        print(flagged_line(row))
    print(summary_line(report))
    return EXIT_OK
