"""The coach-derived blocks of the Coach tab, as the app reads them.

Everything here is the coach's own answer (``leetcode_coach.progress`` for
progress and re-tests, ``leetcode_coach.how_to`` for the commands and the
method) plus the facts a screen needs around it: each cluster's problem list
with title and URL, its position, and the command for a due re-test. No rule
of the coach is re-derived. Each function raises if the coach does; the
caller (``_coach_log._from_coach``) turns that into ``None`` + a warning.

``next`` is the coach's first problem with no ``code`` event. ``leetcode
--cluster`` also skips problems LeetCode reports Accepted, which needs the
network and so never runs in the per-minute push; ``how_to.NEXT_NOTE`` tells
the reader.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from leetcode_coach import how_to
from leetcode_coach import progress as coach_progress
from leetcode_guard._constants import PROBLEM_URL_TEMPLATE

if TYPE_CHECKING:
    from pathlib import Path


def clusters_view(folder: Path) -> dict[str, dict[str, Any]]:
    """Per cluster: the coach's counts and ``next``, plus order and problems.

    ``order`` is the curriculum position: the snapshot is serialised with
    sorted keys, so the dict's own order does not survive the trip.
    """
    listed = coach_progress.load_clusters()
    view: dict[str, dict[str, Any]] = {}
    for order, (name, stats) in enumerate(
        coach_progress.cluster_progress(folder).items()
    ):
        view[name] = {
            **stats,
            "order": order,
            "problems": [
                {
                    "slug": p["slug"],
                    "number": p["id"],
                    "title": p.get("title"),
                    "url": PROBLEM_URL_TEMPLATE.format(slug=p["slug"]),
                }
                for p in listed[name]
            ],
        }
    return view


def retests_view(folder: Path) -> list[dict[str, Any]]:
    """The coach's due re-tests, each with the command that starts it."""
    return [
        {**row, "command": how_to.retest_command(row["slug"])}
        for row in coach_progress.due_retests(folder)
    ]


def how_to_view(_folder: Path) -> dict[str, Any]:
    """The commands and the method, first command on the first cluster."""
    return how_to.block(next(iter(coach_progress.load_clusters()), None))
