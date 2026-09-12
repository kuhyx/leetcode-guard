"""The suggestion list while the lock is up. Continued from :mod:`test_scenarios`.

One story, end to end: a day that costs two credits, one of the suggested
problems solved, and the list it leaves behind. Written at the guard level
rather than against ``build_problem_lines`` because the bug was not in the
formatting -- every layer below this one was already correct, and the list
still sat there because nothing asked it to change.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from leetcode_guard._submissions import ProbeStatus, SolveProbe
from leetcode_guard.tests._guard_factories import create_guard, pool_of, probe_of
from leetcode_guard.tests._ledger_fixtures import MONDAY, NOW, TUESDAY, submission

if TYPE_CHECKING:
    from pathlib import Path

TUESDAY_MORNING = datetime.combine(TUESDAY, NOW.timetz())


def accepted(slug: str) -> SolveProbe:
    """A probe reporting one fresh accepted submission for ``slug``."""
    return SolveProbe(
        status=ProbeStatus.OK,
        submissions=(submission("new-1", slug),),
        reason="1 recent",
    )


def owing_guard(tmp_path: Path, hmac_key: Path, *, poll_probe: SolveProbe):
    """A guard on a day that costs two credits, suggesting three problems.

    Two is the smallest demand that can show the bug: with one owed, the
    first accepted submission unlocks the machine and the list stops
    mattering a second later.
    """
    guard, _ = create_guard(
        tmp_path,
        demo_mode=False,
        probe=probe_of("old-1"),
        poll_probe=poll_probe,
        pool=pool_of("alpha", "beta", "gamma"),
        key_file=hmac_key,
        now=TUESDAY_MORNING,
    )
    return guard


def titles(guard) -> list[str]:
    """The problem names currently on the surface, in display order."""
    return [
        line.label.split(". ", 1)[1].split("  --")[0] for line in guard._model.problems
    ]


def test_a_problem_solved_mid_lock_stops_being_suggested(
    tmp_path: Path, hmac_key: Path, debt_starts
):
    """The reported bug.

    Monday's gate never charged, so Tuesday costs two. Solving Alpha earns
    one of them and leaves the lock up -- and Alpha, which can never earn the
    second, was still occupying the top slot. It now drops out and Beta and
    Gamma move up, renumbered.
    """
    debt_starts(MONDAY)
    guard = owing_guard(tmp_path, hmac_key, poll_probe=accepted("alpha"))
    assert titles(guard) == ["Alpha", "Beta", "Gamma"]

    guard._on_poll_result(guard._check())

    assert guard._decision().locked, "one solve of the two owed must not unlock"
    assert titles(guard) == ["Beta", "Gamma"]
    assert guard._model.problems[0].label.startswith("1. Beta")


def test_the_solve_is_credited_where_the_row_used_to_be(
    tmp_path: Path, hmac_key: Path, debt_starts
):
    """Losing the row must not lose the news that the submission registered."""
    debt_starts(MONDAY)
    guard = owing_guard(tmp_path, hmac_key, poll_probe=accepted("alpha"))

    guard._on_poll_result(guard._check())

    assert guard._model.status_line.startswith("Accepted: Alpha -- need 1 more solve")


def test_a_solve_outside_the_suggestions_leaves_the_list_alone(
    tmp_path: Path, hmac_key: Path, debt_starts
):
    """Any accepted submission counts, so most solves touch no row at all.

    The list must not reshuffle or announce anything when the user solved
    something the surface never named.
    """
    debt_starts(MONDAY)
    guard = owing_guard(tmp_path, hmac_key, poll_probe=accepted("something-else"))

    guard._on_poll_result(guard._check())

    assert titles(guard) == ["Alpha", "Beta", "Gamma"]
    assert "Accepted:" not in guard._model.status_line
