"""The finish credit's scope: the current unit, the poll that moves on, cannot check."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from leetcode_guard import _theory_finish
from leetcode_guard._ledger_entries import credit_entry
from leetcode_guard._ledger_io import Ledger, append
from leetcode_guard._phase import PhaseState
from leetcode_guard._theory_credit import (
    due_credits,
    minutes_into_credit,
    theory_credits,
)
from leetcode_guard.tests._finish_fixtures import (
    A_ID,
    B1_ID,
    DAY,
    NOW,
    TODAY,
    flips,
    ids,
    poll,
    solved_a1,
)
from leetcode_guard.tests._ledger_fixtures import submission
from leetcode_guard.tests._theory_scenario import taught, world
from leetcode_guard.tests._tutor_fixtures import ALGO, state_row, write_tutor

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_a_module_of_a_unit_that_is_not_current_pays_nothing(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """The backfill trap: b1 is done today (never taught) while SOLVE(a) is current."""
    world(tmp_path, monkeypatch)
    taught(hmac_key, NOW)
    flips(hmac_key, ("a", True, TODAY), ("b1", True, TODAY), ("b2", True, TODAY))

    result = poll(Ledger(), data_dir, hmac_key)

    assert result.state is not None
    assert result.state.unit == "a"
    assert ids(result) == [A_ID]


def test_the_flip_poll_pays_and_so_does_the_poll_that_moves_on(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """THEORY(a) -> SOLVE(a) pays on the flip; a finished unit pays on the move to b."""
    world(tmp_path, monkeypatch)
    taught(hmac_key, NOW)
    flips(hmac_key)
    ledger = Ledger()
    assert poll(ledger, data_dir, hmac_key).minted == ()

    flips(hmac_key, ("a", True, TODAY))
    flip = poll(ledger, data_dir, hmac_key)
    assert (flip.state.phase if flip.state else None, ids(flip)) == ("solve", [A_ID])

    other = Ledger()
    flips(hmac_key)
    assert poll(other, data_dir, hmac_key).minted == ()
    flips(hmac_key, ("a", True, TODAY))
    solved_a1(other, hmac_key)
    moved = poll(other, data_dir, hmac_key)
    assert (moved.state.unit if moved.state else None, ids(moved)) == ("b", [A_ID])


def test_every_unit_finished_still_pays_the_unit_it_just_left(
    tmp_path, monkeypatch, hmac_key: Path
):
    """The move into ``none`` is a move on too."""
    world(tmp_path, monkeypatch)
    taught(hmac_key, NOW)
    ledger = Ledger()
    solved_a1(ledger, hmac_key)
    append(
        ledger,
        [credit_entry(submission("2", "b1-easy"), day=DAY, now=NOW, key_file=hmac_key)],
    )
    flips(hmac_key, ("a", True, TODAY), ("b1", True, TODAY), ("b2", True, TODAY))
    ahead = _theory_finish.due_finish(
        ledger,
        PhaseState("b", "theory", ALGO, ("b1", "b2")),
        PhaseState("", "none"),
        stamp=(DAY, NOW),
        key_file=hmac_key,
    )
    assert [e.entry_id for e in ahead] == [B1_ID, f"theory-done:{ALGO}:b2"]
    left = _theory_finish.due_finish(
        ledger,
        PhaseState("", "none"),
        PhaseState("a", "solve"),
        stamp=(DAY, NOW),
        key_file=hmac_key,
    )
    assert [e.entry_id for e in left] == [A_ID]
    unknown = PhaseState("zzz", "solve")
    assert not _theory_finish.due_finish(
        ledger, PhaseState("", "none"), unknown, stamp=(DAY, NOW), key_file=hmac_key
    )


def test_cannot_check_mints_nothing_and_warns(
    tmp_path,
    monkeypatch,
    data_dir: Path,
    hmac_key: Path,
    caplog: pytest.LogCaptureFixture,
):
    """One unverified C2 row: the phase and the finish are both 'cannot check'."""
    world(tmp_path, monkeypatch)
    taught(hmac_key, NOW)
    good = state_row("a", done=True, at=TODAY, key_file=hmac_key)
    forged = {**state_row("b1", done=True, at=TODAY, key_file=hmac_key), "hmac": "0"}
    write_tutor("module_state.json", [good, forged])

    with caplog.at_level(logging.WARNING):
        result = poll(Ledger(), data_dir, hmac_key)
        direct = _theory_finish.due_finish(
            Ledger(),
            PhaseState("a", "solve", ALGO, ("a",)),
            None,
            stamp=(DAY, NOW),
            key_file=hmac_key,
        )

    assert (result.state, result.minted, direct) == (None, (), [])
    assert "cannot check" in caplog.text
    assert not (data_dir / "ledger.json").exists()


def test_a_finish_credit_is_not_a_minute_credit(hmac_key: Path):
    """``due_credits`` and ``minutes_into_credit`` ignore it; ``theory_credits`` counts it."""
    state = PhaseState("a", "solve", ALGO, ("a",))
    ledger = Ledger()
    stamp = (DAY, NOW)
    finish = _theory_finish.finish_entry(
        stamp, unit="a", subject=ALGO, module="a", key_file=hmac_key
    )
    append(ledger, [finish])

    fresh = due_credits(ledger, state, 12, stamp=stamp, key_file=hmac_key)

    assert [e.entry_id for e in fresh] == [f"theory:{DAY}:1"]
    assert [minutes_into_credit(ledger, state, m, day=DAY) for m in (0, 7, 12)] == [
        0,
        7,
        12,
    ]
    assert theory_credits(ledger, day=DAY) == (1, 1)
    assert theory_credits(ledger, day=DAY + timedelta(days=1)) == (0, 1)


def test_without_a_curriculum_only_the_current_unit_can_pay(
    monkeypatch, hmac_key: Path
):
    """The unit the poll left cannot be looked up: the current unit still pays."""
    monkeypatch.setattr(_theory_finish, "load_curriculum", lambda: None)
    write_tutor(
        "module_state.json",
        [state_row("a", done=True, at=TODAY, key_file=hmac_key)],
    )

    left = _theory_finish.due_finish(
        Ledger(),
        PhaseState("b", "theory", ALGO, ("b1",)),
        PhaseState("a", "solve"),
        stamp=(DAY, NOW),
        key_file=hmac_key,
    )

    assert left == []
