"""Theory credits: 12 signed teaching minutes on the current unit pay 1 credit."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
from typing import TYPE_CHECKING

from leetcode_guard import _phase_file, _theory_credit, _tutor_signed
from leetcode_guard._balance import compute_balance
from leetcode_guard._difficulty import WeightTable
from leetcode_guard._gate_today import decide_today
from leetcode_guard._ledger_entries import credit_entry
from leetcode_guard._ledger_io import Ledger, append, load_ledger
from leetcode_guard._phase import PhaseState
from leetcode_guard._theory_credit import due_credits, poll_theory, theory_entry
from leetcode_guard.tests._ledger_fixtures import submission
from leetcode_guard.tests._theory_scenario import began, states, taught, world
from leetcode_guard.tests._tutor_fixtures import ALGO, state_row, write_tutor

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

NOW = datetime(2026, 11, 24, 12, 0).astimezone()  # a Tuesday: the day costs 2
DAY = NOW.date()


def poll(ledger: Ledger, data_dir: Path, key: Path) -> _theory_credit.TheoryPoll:
    """One poll against the scratch ledger file."""
    return poll_theory(ledger, data_dir / "ledger.json", day=DAY, now=NOW, key_file=key)


def test_24_minutes_in_theory_mint_two_credits_and_pay_the_day(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """THEORY(a): 10 + 14 minutes on a's module -> theory:<day>:1 and :2."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    began(hmac_key)
    taught(hmac_key, NOW, ("a", 10), ("a", 14))
    ledger = Ledger()

    result = poll(ledger, data_dir, hmac_key)

    assert result.state is not None
    assert (result.state.unit, result.state.phase, result.minutes) == (
        "a",
        "theory",
        24,
    )
    ids = [entry.entry_id for entry in result.minted]
    assert ids == [f"theory:{DAY}:1", f"theory:{DAY}:2"]
    assert result.minted[1].detail == {
        "source": "tutor-theory",
        "unit": "a",
        "minutes": "24",
    }
    assert set(load_ledger(data_dir / "ledger.json", key_file=hmac_key).entries) == set(
        ids
    )
    assert poll(ledger, data_dir, hmac_key).minted == ()
    weights = WeightTable(levels={})
    assert (
        compute_balance(
            load_ledger(data_dir / "ledger.json", key_file=hmac_key), weights
        ).available
        == 2
    )
    assert not decide_today(ledger, day=DAY, now=NOW, key_file=hmac_key).locked


def test_other_modules_and_review_rows_mint_nothing(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """b's module (learning ahead) and a review row (no module) never pay."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    taught(hmac_key, NOW, ("b1", 30), (None, 30))

    result = poll(Ledger(), data_dir, hmac_key)

    assert (result.minutes, result.minted) == (0, ())


def test_solve_pays_minutes_taught_before_done_and_none_after(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """SOLVE(a): teachable is empty; 12 minutes before the flip pay, 30 after do not."""
    world(tmp_path, monkeypatch)
    flip = (NOW - timedelta(minutes=1, seconds=30)).timestamp()
    states(hmac_key, "a", at=flip)
    began(hmac_key)
    taught(hmac_key, NOW, ("a", 12), ("a", 30))

    result = poll(Ledger(), data_dir, hmac_key)

    assert result.state is not None
    assert (result.state.phase, result.state.teachable) == ("solve", ())
    assert result.minutes == 12
    # One minute credit (the 30 after the flip never pay), plus a's finish credit.
    assert [e.entry_id for e in result.minted] == [
        f"theory:{DAY}:1",
        f"theory-done:{ALGO}:a",
    ]


def test_every_easy_solved_moves_on_to_the_next_units_theory(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """a done and a1 solved: THEORY(b), b's modules teachable; b's minutes from
    before THEORY(b) began pay nothing (``theory_since``), later ones pay."""
    world(tmp_path, monkeypatch)
    states(hmac_key, "a")
    taught(hmac_key, NOW, ("b2", 12))
    ledger = load_ledger(data_dir / "ledger.json", key_file=hmac_key)
    append(
        ledger,
        [credit_entry(submission("1", "a1"), day=DAY, now=NOW, key_file=hmac_key)],
    )

    result = poll(ledger, data_dir, hmac_key)

    assert result.state is not None
    assert (result.state.unit, result.state.phase) == ("b", "theory")
    assert result.state.teachable == ((ALGO, "b1"), (ALGO, "b2"))
    assert result.minted == ()
    taught(hmac_key, NOW + timedelta(minutes=20), ("b2", 12))
    later = NOW + timedelta(minutes=20)
    paid = poll_theory(
        ledger, data_dir / "ledger.json", day=DAY, now=later, key_file=hmac_key
    )
    assert len(paid.minted) == 1


def test_an_unreadable_tutor_ledger_mints_nothing_and_warns(
    tmp_path,
    monkeypatch,
    data_dir: Path,
    hmac_key: Path,
    caplog: pytest.LogCaptureFixture,
):
    """Cannot check is not no: the phase still decides, nothing mints, no raise."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    (_tutor_signed.TUTOR_DIR / "ledger.json").write_text("{torn", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        result = poll(Ledger(), data_dir, hmac_key)

    assert result.state is not None
    assert result.minted == ()
    assert "cannot check" in caplog.text
    assert not (data_dir / "ledger.json").exists()


def test_an_unreadable_module_state_holds_the_last_signed_phase(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """No C2: no decision, nothing minted, and C3 is left exactly as it was."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    taught(hmac_key, NOW, ("a", 24))
    poll(Ledger(), data_dir, hmac_key)
    before = _phase_file.PHASE_FILE.read_bytes()
    (_tutor_signed.TUTOR_DIR / "module_state.json").unlink()

    result = poll(Ledger(), data_dir, hmac_key)

    assert (result.state, result.minted) == (None, ())
    assert _phase_file.PHASE_FILE.read_bytes() == before


def test_a_bug_in_the_poll_never_raises(
    monkeypatch, data_dir: Path, hmac_key: Path, caplog: pytest.LogCaptureFixture
):
    """Whatever breaks costs the theory credit, never the lock."""

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError

    monkeypatch.setattr(_theory_credit, "gather_phase", boom)

    with caplog.at_level(logging.WARNING):
        assert poll(Ledger(), data_dir, hmac_key).state is None

    assert "theory poll failed: RuntimeError" in caplog.text


def test_numbering_runs_over_the_day_and_skips_taken_ids(hmac_key: Path):
    """A unit switch keeps counting the day; a taken id is never reused."""
    ledger = Ledger()
    old = theory_entry((DAY, NOW), n=2, unit="a", minutes=12, key_file=hmac_key)
    ledger.entries[old.entry_id] = old
    state = PhaseState("b", "theory", ALGO, ("b1",))

    fresh = due_credits(ledger, state, 25, stamp=(DAY, NOW), key_file=hmac_key)

    assert [e.entry_id for e in fresh] == [f"theory:{DAY}:3", f"theory:{DAY}:4"]
    assert due_credits(ledger, PhaseState("", "none"), 99, stamp=(DAY, NOW)) == []


def test_nothing_is_read_when_nothing_can_pay():
    """In ``none`` (or a unit with no module) the tutor ledger is not even opened."""
    assert _theory_credit.paying_minutes(PhaseState("", "none"), day=DAY) == 0
    assert json.dumps(_theory_credit.MINUTES_PER_CREDIT) == "12"


def test_minutes_into_credit_follows_the_due_rule(hmac_key: Path):
    """0..12; 12 only while a mint is pending; never negative; none has no next."""
    state = PhaseState(unit="a", phase="theory", subject=ALGO, modules=("a",))
    ledger = Ledger()
    stamp = (DAY, NOW)

    def into(minutes: int, phase_state: PhaseState = state) -> int:
        return _theory_credit.minutes_into_credit(ledger, phase_state, minutes, day=DAY)

    assert [into(m) for m in (0, 7, 11, 12, 30)] == [0, 7, 11, 12, 12]
    append(ledger, due_credits(ledger, state, 24, stamp=stamp, key_file=hmac_key))
    assert [into(m) for m in (24, 30, 36, 40)] == [0, 6, 12, 12]
    assert into(5) == 0
    assert into(30, PhaseState(unit="b", phase="theory")) == 12
    assert into(30, PhaseState(unit="", phase="none")) == 0


def test_one_bad_row_in_module_state_mints_nothing_and_holds_the_phase(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """The one rule for C2 (both repos' docs): a row that fails its signature
    makes the whole file "cannot check". Dropping it instead could only un-do a
    module and pay its theory again; held, solves still pay and the lock keeps
    its Open rows, hatch and break-glass (the THEORY card is only a slot)."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    taught(hmac_key, NOW, ("a", 24))
    poll(Ledger(), data_dir, hmac_key)
    before = _phase_file.PHASE_FILE.read_bytes()
    good = state_row("b", done=False, at=1.0, key_file=hmac_key)
    bad = state_row("a", done=False, at=2.0, key_file=hmac_key)
    bad["hmac"] = "0" + str(bad["hmac"])
    write_tutor("module_state.json", [good, bad])

    result = poll(Ledger(), data_dir, hmac_key)

    assert (result.state, result.minted) == (None, ())
    assert _phase_file.PHASE_FILE.read_bytes() == before
