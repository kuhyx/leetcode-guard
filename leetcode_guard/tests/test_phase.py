"""The theory-first state machine and the inputs it reads."""

from __future__ import annotations

from datetime import UTC, date, datetime
import json
import logging
from typing import TYPE_CHECKING

from leetcode_guard import _constants, _curriculum
from leetcode_guard._curriculum import Curriculum, parse_curriculum
from leetcode_guard._ledger_entries import credit_entry, seen_entry
from leetcode_guard._ledger_io import Ledger, append
from leetcode_guard._phase import NONE_STATE, PhaseState, decide_phase
from leetcode_guard._phase_inputs import (
    easy_by_unit,
    gather_phase,
    trusted_solved_slugs,
)
from leetcode_guard._pool_cache import CachedPool, write_cache
from leetcode_guard.tests._ledger_fixtures import submission
from leetcode_guard.tests._tutor_fixtures import ALGO, state_row, write_tutor
from leetcode_guard.tests.test_problem import make

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

DOCUMENT = {
    "units": [
        {"id": "a", "tags": ["x"], "tutor": {"subject": ALGO, "modules": ["a"]}},
        {"id": "b", "tags": ["y"], "tutor": {"subject": ALGO, "modules": ["b1", "b2"]}},
        {"id": "free", "tags": ["z"]},
    ]
}
NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
DAY = date(2026, 11, 22)


def curriculum() -> Curriculum:
    """Two mapped units and one with nothing to teach."""
    parsed = parse_curriculum(DOCUMENT)
    assert parsed is not None
    return parsed


EASY = (frozenset({"a1", "a2"}), frozenset({"b1"}), frozenset({"z1"}))


def done(*modules: str) -> dict[tuple[str, str], bool]:
    """Every named module done."""
    return {(ALGO, module): True for module in modules}


def test_nothing_taught_is_theory_of_the_first_unit():
    """THEORY(a): a's modules are teachable, its problems are counted."""
    state = decide_phase(curriculum(), EASY, frozenset({"a1"}), {})

    assert state == PhaseState("a", "theory", ALGO, ("a",), solved=1, total=2)
    assert state.teachable == ((ALGO, "a"),)


def test_theory_done_with_problems_left_is_solve_and_teaches_nothing():
    """SOLVE(a): no module is teachable, the count still shows."""
    state = decide_phase(curriculum(), EASY, frozenset({"a1"}), done("a"))

    assert (state.unit, state.phase, state.teachable) == ("a", "solve", ())


def test_every_easy_solved_moves_to_the_next_units_theory():
    """No learning ahead: b becomes current only once a is finished."""
    state = decide_phase(curriculum(), EASY, frozenset({"a1", "a2"}), done("a", "b1"))

    assert (state.unit, state.phase) == ("b", "theory")
    assert state.teachable == ((ALGO, "b1"), (ALGO, "b2"))


def test_solving_ahead_does_not_skip_theory():
    """All of a's problems solved but its theory not done: still THEORY(a)."""
    state = decide_phase(curriculum(), EASY, frozenset({"a1", "a2"}), {})

    assert (state.unit, state.phase) == ("a", "theory")


def test_a_unit_with_nothing_to_teach_needs_only_its_problems():
    """``free`` maps no tutor module: SOLVE straight away, then none."""
    taught = done("a", "b1", "b2")
    solved = frozenset({"a1", "a2", "b1"})

    assert decide_phase(curriculum(), EASY, solved, taught).phase == "solve"
    assert decide_phase(curriculum(), EASY, solved | {"z1"}, taught) == NONE_STATE
    assert NONE_STATE.teachable == ()


def test_rework_puts_the_unit_back_in_theory():
    """A module flipping back to not done reopens its unit's THEORY."""
    flipped = {**done("a"), (ALGO, "a"): False}

    assert decide_phase(curriculum(), EASY, frozenset(), flipped).phase == "theory"


def test_easy_sets_leave_out_premium_and_harder_problems():
    """A premium Easy could never be solved: it must not hold a unit open."""
    problems = [
        make("a1", topics=["x"]),
        make("a-paid", topics=["x"], paid_only=True),
        make("a-medium", topics=["x"], difficulty="Medium"),
        make("stray", topics=["nope"]),
    ]

    assert easy_by_unit(curriculum(), problems) == (
        frozenset({"a1"}),
        frozenset(),
        frozenset(),
    )


def test_only_trusted_solves_count(hmac_key: Path, missing_key: Path):
    """A forged credit is not a solve; a seen marker is."""
    ledger = Ledger()
    good = credit_entry(submission("1", "a1"), day=DAY, now=NOW, key_file=hmac_key)
    seen = seen_entry(submission("2", "a2"), day=DAY, now=NOW, key_file=hmac_key)
    forged = credit_entry(submission("3", "b1"), day=DAY, now=NOW, key_file=missing_key)
    append(ledger, [good, seen, forged])

    assert trusted_solved_slugs(ledger) == frozenset({"a1", "a2"})


def _scratch_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A scratch curriculum and pool; the C2 file is the test's to write."""
    path = tmp_path / "curriculum.json"
    path.write_text(json.dumps(DOCUMENT), encoding="utf-8")
    monkeypatch.setattr(_curriculum, "CURRICULUM_FILE", path)
    pool = (make("a1", topics=["x"]), make("b1", topics=["y"]))
    write_cache(
        _constants.POOL_CACHE_FILE,
        CachedPool(problems=pool, fetched_at=0.0, complete=True),
    )


def test_gather_reads_signed_state_from_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hmac_key: Path
):
    """End to end from files: a's module done, a1 unsolved -> SOLVE(a)."""
    _scratch_inputs(tmp_path, monkeypatch)
    write_tutor(
        "module_state.json", [state_row("a", done=True, at=1.0, key_file=hmac_key)]
    )

    state = gather_phase(Ledger(), key_file=hmac_key)

    assert state is not None
    assert (state.unit, state.phase, state.solved, state.total) == ("a", "solve", 0, 1)


def test_any_unreadable_input_is_cannot_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    hmac_key: Path,
    caplog: pytest.LogCaptureFixture,
):
    """No curriculum, no pool, no C2 file: ``None`` each time, never a phase."""
    with caplog.at_level(logging.WARNING):
        assert gather_phase(Ledger(), key_file=hmac_key) is None
        path = tmp_path / "curriculum.json"
        path.write_text(json.dumps(DOCUMENT), encoding="utf-8")
        monkeypatch.setattr(_curriculum, "CURRICULUM_FILE", path)
        assert gather_phase(Ledger(), key_file=hmac_key) is None
        _scratch_inputs(tmp_path, monkeypatch)
        assert gather_phase(Ledger(), key_file=hmac_key) is None

    assert "no curriculum" in caplog.text
    assert "no problem pool" in caplog.text


def test_a_c2_row_that_fails_its_signature_is_cannot_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    hmac_key: Path,
    caplog: pytest.LogCaptureFixture,
):
    """Dropping a forged C2 row could only un-do a module, which pays theory again.

    A row that does not verify is a module state nobody can read, so the file
    is "cannot check" (found by the 2026-11-22 e2e: a forged ``done`` row put
    SOLVE(a) back in THEORY and minted the day's theory credits).
    """
    _scratch_inputs(tmp_path, monkeypatch)
    forged = state_row("a", done=True, at=2.0, key_file=hmac_key)
    forged["hmac"] = "0" + str(forged["hmac"])
    write_tutor(
        "module_state.json",
        [state_row("a", done=True, at=1.0, key_file=hmac_key), forged],
    )

    with caplog.at_level(logging.WARNING):
        assert gather_phase(Ledger(), key_file=hmac_key) is None

    assert "cannot check" in caplog.text
