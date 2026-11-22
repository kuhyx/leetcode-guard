"""Rework (phase 2): a module flipped back to not done reopens THEORY and pays again.

kuhy, 2026-11-22: the ``?`` button's chat adds cards to the unit's first module,
the tutor writes C2 ``done: false`` for it, and the lock returns to THEORY(u)
"until the new cards are taught, and those teaching minutes pay again", with
no cap on that pay. Re-entry starts ``theory_since`` over, so minutes taught
while the unit sat in SOLVE (after it was done) never pay.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from leetcode_guard._ledger_io import Ledger
from leetcode_guard._phase_file import phase_since
from leetcode_guard._theory_credit import poll_theory
from leetcode_guard.tests._theory_scenario import began, world
from leetcode_guard.tests._tutor_fixtures import (
    ALGO,
    state_row,
    teaching_row,
    write_tutor,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

NOW = datetime(2026, 11, 24, 12, 0).astimezone()
DONE_AT = NOW - timedelta(hours=2)
REWORK_AT = NOW - timedelta(minutes=80)
REENTRY = NOW - timedelta(minutes=79)
"""The harvester's next minute after the tutor wrote ``done: false``."""


def _poll(ledger: Ledger, data_dir: Path, key: Path, at: datetime) -> list[str]:
    """One poll at ``at``; the ids it minted."""
    result = poll_theory(
        ledger, data_dir / "ledger.json", day=at.date(), now=at, key_file=key
    )
    return [entry.entry_id for entry in result.minted]


def _c2(key: Path, *rows: tuple[bool, datetime]) -> None:
    """Module ``a``'s C2 history, oldest first."""
    write_tutor(
        "module_state.json",
        [
            state_row("a", done=done, at=at.timestamp(), key_file=key, n=n)
            for n, (done, at) in enumerate(rows, start=1)
        ],
    )


def test_rework_reopens_theory_and_pays_new_minutes_without_a_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, data_dir: Path, hmac_key: Path
):
    """SOLVE(a) -> done: false -> THEORY(a) again; 36 new minutes pay 3, none older."""
    world(tmp_path, monkeypatch)
    began(hmac_key, "a", "solve")
    _c2(hmac_key, (True, DONE_AT))
    ledger = Ledger()
    _poll(ledger, data_dir, hmac_key, DONE_AT + timedelta(minutes=1))

    _c2(hmac_key, (True, DONE_AT), (False, REWORK_AT))
    assert _poll(ledger, data_dir, hmac_key, REENTRY) == []

    # 30 minutes taught while a sat in SOLVE (after done, before the rework),
    # then the new cards: 3 x 12 minutes after the re-entry.
    in_solve = NOW - timedelta(minutes=90)
    rows: list[object] = [
        teaching_row("s0-m30", 30, ended=in_solve, key_file=hmac_key, where=(ALGO, "a"))
    ]
    rows += [
        teaching_row(
            f"s{i}-m12",
            12,
            ended=NOW - timedelta(minutes=40 - 13 * i),
            key_file=hmac_key,
            where=(ALGO, "a"),
        )
        for i in range(1, 4)
    ]
    write_tutor("ledger.json", rows)

    minted = _poll(ledger, data_dir, hmac_key, NOW)

    day = NOW.date()
    assert minted == [f"theory:{day}:1", f"theory:{day}:2", f"theory:{day}:3"]


def test_reentry_starts_theory_since_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, data_dir: Path, hmac_key: Path
):
    """C3's ``theory_since`` is the re-entry poll, not the unit's first THEORY."""
    world(tmp_path, monkeypatch)
    began(hmac_key, "a", "solve")
    _c2(hmac_key, (True, DONE_AT))
    ledger = Ledger()
    _poll(ledger, data_dir, hmac_key, DONE_AT + timedelta(minutes=1))
    _c2(hmac_key, (True, DONE_AT), (False, REWORK_AT))

    result = poll_theory(
        ledger, data_dir / "ledger.json", day=NOW.date(), now=REENTRY, key_file=hmac_key
    )

    assert result.state is not None
    assert (result.state.unit, result.state.phase) == ("a", "theory")
    assert phase_since(result.state, key_file=hmac_key) == REENTRY.timestamp()


def test_done_again_after_rework_mints_no_second_finish_credit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, data_dir: Path, hmac_key: Path
):
    """The finish credit is once per module; the rework pays by minutes only."""
    world(tmp_path, monkeypatch)
    began(hmac_key, "a", "solve")
    _c2(hmac_key, (True, DONE_AT))
    ledger = Ledger()
    _poll(ledger, data_dir, hmac_key, DONE_AT + timedelta(minutes=1))
    _c2(hmac_key, (True, DONE_AT), (False, REWORK_AT))
    _poll(ledger, data_dir, hmac_key, REENTRY)
    _c2(
        hmac_key,
        (True, DONE_AT),
        (False, REWORK_AT),
        (True, NOW - timedelta(minutes=5)),
    )

    assert _poll(ledger, data_dir, hmac_key, NOW) == []
