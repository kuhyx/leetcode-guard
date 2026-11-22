"""The last teaching turn of a unit pays, even when C2 is stamped just before it.

The tutor writes the module-state row (C2 ``at``) after the credit row of the
turn that finished the module (C1 ``ended_at``), so the turn's end is normally
at or before the moment theory became done. Both are wall-clock stamps from
separate writes; a reorder by a second or two must not silently drop the turn
that finished the unit (``_tutor_signed.UNTIL_SLACK_S``).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from leetcode_guard._ledger_io import Ledger
from leetcode_guard._theory_credit import poll_theory
from leetcode_guard._tutor_signed import UNTIL_SLACK_S, teaching_minutes
from leetcode_guard.tests._theory_scenario import began, states, taught, world
from leetcode_guard.tests._tutor_fixtures import ALGO, teaching_row

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 11, 24, 12, 0).astimezone()
DAY = NOW.date()
LAST_END = NOW - timedelta(minutes=1)  # ``taught`` ends its last span here


def test_last_teaching_turn_pays_when_c2_is_stamped_a_second_before_it(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """6 + 6 minutes finish module a; C2 says done 1 s before the 2nd ended."""
    world(tmp_path, monkeypatch)
    began(hmac_key)
    taught(hmac_key, NOW, ("a", 6), ("a", 6))
    states(hmac_key, "a", at=LAST_END.timestamp() - 1)

    result = poll_theory(
        Ledger(), data_dir / "ledger.json", day=DAY, now=NOW, key_file=hmac_key
    )

    assert result.state is not None
    assert (result.state.unit, result.state.phase) == ("a", "solve")
    assert result.minutes == 12
    assert [e.entry_id for e in result.minted] == [f"theory:{DAY}:1"]


def test_last_teaching_turn_slack_is_a_boundary_not_a_window(hmac_key: Path):
    """At ``until + slack`` the turn pays; a hair later it does not."""
    until = LAST_END.timestamp()

    def minutes_ending(after: float) -> int:
        row = teaching_row(
            "s-m6",
            6,
            ended=LAST_END + timedelta(seconds=after),
            key_file=hmac_key,
            where=(ALGO, "a"),
        )
        return teaching_minutes([row], ALGO, ("a",), day=DAY, window=(None, until))

    assert minutes_ending(UNTIL_SLACK_S) == 6
    assert minutes_ending(UNTIL_SLACK_S + 0.01) == 0
