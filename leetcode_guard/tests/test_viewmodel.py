"""Tests for the lock's text. No Tk involved."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from leetcode_guard._auth import AuthState, Cookies
from leetcode_guard._gate import GateState, decide
from leetcode_guard._ledger import LedgerEntry
from leetcode_guard._ledger_io import Ledger, append, load_ledger, save_ledger
from leetcode_guard._pool_resolve import PoolResolution
from leetcode_guard._problem import parse_problem
from leetcode_guard._submissions import ProbeStatus, SolveProbe
from leetcode_guard._viewmodel import build_problem_lines, build_viewmodel
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    NOW,
    SATURDAY,
    add_charge,
    forged_credit,
    ledger_with_credits,
)
from leetcode_guard.tests._net_fixtures import problem_row

if TYPE_CHECKING:
    from pathlib import Path

CHECKED_AT = datetime(2026, 7, 27, 12, 4, 31, tzinfo=timezone.utc)
SIGNED_OUT = AuthState(cookies=None, note="signed out note")
OK_PROBE = SolveProbe(status=ProbeStatus.OK, submissions=(), reason="none recently")
BLIND_PROBE = SolveProbe(
    status=ProbeStatus.UNVERIFIABLE,
    submissions=(),
    reason="cannot reach LeetCode: down",
)


def pool_of(*slugs: str, notes: tuple[str, ...] = ()) -> PoolResolution:
    problems = tuple(
        p for p in (parse_problem(problem_row(slug)) for slug in slugs) if p is not None
    )
    return PoolResolution(problems=problems, source="cache", notes=notes)


def model_for(ledger: Ledger, *, day=MONDAY, probe=OK_PROBE, key_file=None, **kwargs):
    decision = decide(ledger, day=day, now=NOW, key_file=key_file)
    return build_viewmodel(
        decision,
        kwargs.pop("pool", pool_of()),
        kwargs.pop("auth", SIGNED_OUT),
        probe,
        checked_at=CHECKED_AT,
        limit=kwargs.pop("limit", 10),
        **kwargs,
    )


def test_locked_headline_names_the_shortfall(hmac_key: Path):
    model = model_for(Ledger(), key_file=hmac_key)

    assert model.headline == "Solve 1 LeetCode problem to unlock"
    assert not model.unlocked


def test_a_weekend_shortfall_is_pluralised(hmac_key: Path):
    model = model_for(Ledger(), day=SATURDAY, key_file=hmac_key)

    assert model.headline == "Solve 2 LeetCode problems to unlock"
    assert "Saturday costs 2" in model.balance_line
    assert "need 2 more" in model.balance_line


def test_unlocked_headline_reports_what_is_left(hmac_key: Path):
    model = model_for(
        ledger_with_credits(3, day=MONDAY, key_file=hmac_key), key_file=hmac_key
    )

    assert model.headline == "Unlocked -- 2 credits left"
    assert model.unlocked
    assert "need" not in model.balance_line


def test_one_remaining_credit_is_singular(hmac_key: Path):
    model = model_for(
        ledger_with_credits(2, day=MONDAY, key_file=hmac_key), key_file=hmac_key
    )

    assert model.headline == "Unlocked -- 1 credit left"


def test_a_rolled_back_clock_gets_its_own_headline_and_note(hmac_key: Path):
    ledger = Ledger()
    add_charge(ledger, MONDAY.replace(day=12), key_file=hmac_key)

    model = model_for(ledger, key_file=hmac_key)

    assert model.headline == "Locked -- the system clock moved backwards"
    assert any("earlier than" in note for note in model.notes)


def test_an_unverifiable_probe_says_so_rather_than_saying_not_solved(hmac_key: Path):
    """A blind gate must never render the same sentence a working one would."""
    model = model_for(Ledger(), probe=BLIND_PROBE, key_file=hmac_key)

    assert "Cannot check LeetCode" in model.status_line
    assert "cannot reach LeetCode: down" in model.status_line
    assert "12:04:31" in model.status_line


def test_a_working_probe_reports_watching(hmac_key: Path):
    model = model_for(Ledger(), key_file=hmac_key)

    assert model.status_line.startswith("Watching for an accepted submission")


def test_the_auth_note_is_always_present(hmac_key: Path):
    model = model_for(Ledger(), key_file=hmac_key)

    assert "signed out note" in model.notes


def test_the_auth_note_is_not_duplicated(hmac_key: Path):
    model = model_for(
        Ledger(), key_file=hmac_key, pool=pool_of(notes=("signed out note", "other"))
    )

    assert list(model.notes).count("signed out note") == 1


def test_signed_in_note_is_carried(hmac_key: Path):
    signed_in = AuthState(cookies=Cookies("s", "c"), note="signed in note")

    model = model_for(Ledger(), key_file=hmac_key, auth=signed_in)

    assert "signed in note" in model.notes


def test_an_unreadable_integrity_key_is_announced(missing_key: Path):
    # integrity_ok is set by load_ledger, not by the key argument -- a bare
    # Ledger() defaults to True regardless of what key you pass downstream.
    model = model_for(Ledger(integrity_ok=False), key_file=missing_key)

    assert any("integrity key is unreadable" in note for note in model.notes)


def test_refused_credits_are_announced(tmp_path: Path, hmac_key: Path):
    path = tmp_path / "ledger.json"
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    append(ledger, [forged_credit()])
    save_ledger(path, ledger)

    model = model_for(load_ledger(path, key_file=hmac_key), key_file=hmac_key)

    assert any("1 ledger credits were refused" in note for note in model.notes)


def test_problem_lines_carry_difficulty_acceptance_and_url():
    lines = build_problem_lines(pool_of("two-sum"), limit=10)

    assert lines[0].label.startswith("1. Two Sum")
    assert "Easy" in lines[0].label
    assert "50.0% acceptance" in lines[0].label
    assert lines[0].url == "https://leetcode.com/problems/two-sum/"


def test_the_problem_limit_is_honoured():
    lines = build_problem_lines(pool_of("a", "b", "c"), limit=2)

    assert len(lines) == 2


def test_an_empty_pool_yields_no_lines():
    assert build_problem_lines(pool_of(), limit=10) == ()


def test_the_escape_flag_is_passed_through(hmac_key: Path):
    assert model_for(Ledger(), key_file=hmac_key, show_escape=True).show_escape
    assert not model_for(Ledger(), key_file=hmac_key).show_escape


def test_marker_entries_do_not_affect_the_headline(hmac_key: Path):
    ledger = Ledger()
    append(ledger, [LedgerEntry("ac:seen", "seen", "2026-08-10", "", 0, verified=True)])

    model = model_for(ledger, key_file=hmac_key)

    assert model.headline == "Solve 1 LeetCode problem to unlock"


def test_an_already_charged_day_reads_as_unlocked(hmac_key: Path):
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    add_charge(ledger, MONDAY, key_file=hmac_key)

    decision = decide(ledger, day=MONDAY, now=NOW, key_file=hmac_key)

    assert decision.state is GateState.UNLOCKED_ALREADY_CHARGED
    assert model_for(ledger, key_file=hmac_key).unlocked


def test_the_not_in_force_state_says_so_rather_than_claiming_an_unlock(
    hmac_key: Path, monkeypatch
):
    """It fell through to "Unlocked -- 0 credits left", which is true and
    useless: it never mentions that the gate has not started."""
    from datetime import timedelta

    from leetcode_guard import _gate

    monkeypatch.setattr(_gate, "GATE_START_DATE", MONDAY + timedelta(days=30))

    model = model_for(Ledger(), key_file=hmac_key)

    assert model.headline == "Not in force yet"
    assert model.unlocked
    assert any("does not start until" in note for note in model.notes)
