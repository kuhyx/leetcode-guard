"""Tests for the lock's text. No Tk involved."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from leetcode_guard import _gate
from leetcode_guard import _glyphs as g
from leetcode_guard._auth import AuthState, Cookies
from leetcode_guard._gate import GateState, decide
from leetcode_guard._ledger import LedgerEntry
from leetcode_guard._ledger_io import Ledger, append, load_ledger, save_ledger
from leetcode_guard._pool_resolve import PoolResolution
from leetcode_guard._problem import parse_problem
from leetcode_guard._submissions import ProbeStatus, SolveProbe
from leetcode_guard._viewmodel import build_problem_lines, build_viewmodel
from leetcode_guard._viewmodel_source import ViewSource
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

CHECKED_AT = datetime(2026, 7, 27, 12, 4, 31, tzinfo=UTC)
SIGNED_OUT = AuthState(cookies=None, note="signed out note")
OK_PROBE = SolveProbe(status=ProbeStatus.OK, submissions=(), reason="none recently")
BLIND_PROBE = SolveProbe(
    status=ProbeStatus.UNVERIFIABLE,
    submissions=(),
    reason="cannot reach LeetCode: down",
)


def pool_of(*slugs: str, notes: tuple[str, ...] = ()) -> PoolResolution:
    """A cached pool of the given slugs, carrying the given notes."""
    problems = tuple(
        p for p in (parse_problem(problem_row(slug)) for slug in slugs) if p is not None
    )
    return PoolResolution(problems=problems, source="cache", notes=notes)


def model_for(ledger: Ledger, *, day=MONDAY, probe=OK_PROBE, key_file=None, **kwargs):
    """The view model for ``ledger`` on ``day``; kwargs override the view source."""
    decision = decide(ledger, day=day, now=NOW, key_file=key_file)
    source = ViewSource(
        kwargs.pop("pool", pool_of()),
        kwargs.pop("auth", SIGNED_OUT),
        limit=kwargs.pop("limit", 10),
        solved_slugs=kwargs.pop("solved_slugs", frozenset()),
    )
    return build_viewmodel(decision, source, probe, checked_at=CHECKED_AT, **kwargs)


def test_locked_headline_names_the_shortfall(hmac_key: Path):
    """An empty weekday ledger asks for one solve and stays locked."""
    model = model_for(Ledger(), key_file=hmac_key)

    assert model.headline == g.OWED
    assert model.needed == 1
    assert not model.unlocked


def test_a_weekend_shortfall_is_pluralised(hmac_key: Path):
    """A two-credit weekend day says "problems" and names its cost."""
    model = model_for(Ledger(), day=SATURDAY, key_file=hmac_key)

    assert model.headline == g.OWED * 2
    assert f"{g.TODAY} 2" in model.balance_line
    assert model.needed == 2


def test_unlocked_headline_reports_what_is_left(hmac_key: Path):
    """A paid day unlocks and says how many credits remain."""
    model = model_for(
        ledger_with_credits(3, day=MONDAY, key_file=hmac_key), key_file=hmac_key
    )

    assert model.headline == g.SOLVED
    assert model.unlocked
    assert model.balance_line.startswith(f"{g.CREDIT} 2")
    assert model.needed == 0


def test_one_remaining_credit_is_singular(hmac_key: Path):
    """One remaining credit reads "credit", singular."""
    model = model_for(
        ledger_with_credits(2, day=MONDAY, key_file=hmac_key), key_file=hmac_key
    )

    assert model.balance_line.startswith(f"{g.CREDIT} 1")


def test_a_rolled_back_clock_gets_its_own_headline_and_note(hmac_key: Path):
    """A charge dated after today locks with a clock-moved-backwards headline."""
    ledger = Ledger()
    add_charge(ledger, MONDAY.replace(day=12), key_file=hmac_key)

    model = model_for(ledger, key_file=hmac_key)

    assert model.headline == g.CLOCK_BACK
    assert not model.unlocked


def test_an_unverifiable_probe_says_so_rather_than_saying_not_solved(hmac_key: Path):
    """A blind gate must never render the same mark a working one would."""
    model = model_for(Ledger(), probe=BLIND_PROBE, key_file=hmac_key)

    assert model.status_line == f"{g.BLIND} 12:04:31"
    assert not model.status_ok


def test_a_working_probe_reports_watching(hmac_key: Path):
    """A working probe's status line says it is watching for a solve."""
    model = model_for(Ledger(), key_file=hmac_key)

    assert model.status_line == f"{g.WATCHING} 12:04:31"
    assert model.status_ok


def test_signed_out_is_marked(hmac_key: Path):
    """A signed-out guard shows the signed-out mark among the notes."""
    model = model_for(Ledger(), key_file=hmac_key)

    assert g.SIGNED_OUT in model.notes


def test_pool_sentences_stay_off_the_lock(hmac_key: Path):
    """They are in the status snapshot; the lock keeps only warning marks."""
    model = model_for(
        Ledger(), key_file=hmac_key, pool=pool_of(notes=("signed out note", "other"))
    )

    assert model.notes == (g.SIGNED_OUT,)


def test_signed_in_shows_no_mark(hmac_key: Path):
    """A signed-in guard shows no auth mark at all."""
    signed_in = AuthState(cookies=Cookies("s", "c"), note="signed in note")

    model = model_for(Ledger(), key_file=hmac_key, auth=signed_in)

    assert model.notes == ()


def test_an_unreadable_integrity_key_is_announced(missing_key: Path):
    """A ledger loaded without its key says the integrity key is unreadable."""
    # integrity_ok is set by load_ledger, not by the key argument -- a bare
    # Ledger() defaults to True regardless of what key you pass downstream.
    model = model_for(Ledger(integrity_ok=False), key_file=missing_key)

    assert g.UNSIGNED in model.notes


def test_refused_credits_are_announced(tmp_path: Path, hmac_key: Path):
    """A forged credit refused on load is counted in a note."""
    path = tmp_path / "ledger.json"
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    append(ledger, [forged_credit()])
    save_ledger(path, ledger)

    model = model_for(load_ledger(path, key_file=hmac_key), key_file=hmac_key)

    assert f"{g.REFUSED} 1" in model.notes


def test_problem_lines_carry_difficulty_acceptance_and_url():
    """A problem line shows number, title, difficulty, acceptance and its URL."""
    lines, dropped = build_problem_lines(pool_of("two-sum"), limit=10)

    assert lines[0].label == "1  Two Sum"
    assert lines[0].difficulty == "Easy"
    assert lines[0].mark == f"{g.CREDIT}  50%"
    assert lines[0].url == "https://leetcode.com/problems/two-sum/"
    assert dropped == ()


def test_the_problem_limit_is_honoured():
    """No more problem lines are built than the limit."""
    lines, _ = build_problem_lines(pool_of("a", "b", "c"), limit=2)

    assert len(lines) == 2


def test_an_empty_pool_yields_no_lines():
    """An empty pool gives no lines and nothing dropped."""
    assert build_problem_lines(pool_of(), limit=10) == ((), ())


def test_the_escape_flag_is_passed_through(hmac_key: Path):
    """show_escape reaches the model unchanged."""
    assert model_for(Ledger(), key_file=hmac_key, show_escape=True).show_escape
    assert not model_for(Ledger(), key_file=hmac_key).show_escape


def test_marker_entries_do_not_affect_the_headline(hmac_key: Path):
    """A seen-marker entry does not count as a credit."""
    ledger = Ledger()
    append(ledger, [LedgerEntry("ac:seen", "seen", "2026-08-10", "", 0, verified=True)])

    model = model_for(ledger, key_file=hmac_key)

    assert model.headline == g.OWED


def test_an_already_charged_day_reads_as_unlocked(hmac_key: Path):
    """A day already charged decides as such and renders unlocked."""
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    add_charge(ledger, MONDAY, key_file=hmac_key)

    decision = decide(ledger, day=MONDAY, now=NOW, key_file=hmac_key)

    assert decision.state is GateState.UNLOCKED_ALREADY_CHARGED
    assert model_for(ledger, key_file=hmac_key).unlocked


def test_the_not_in_force_state_says_so_rather_than_claiming_an_unlock(
    hmac_key: Path, monkeypatch
):
    """It fell through to the plain unlocked mark, which is true and useless:
    it never shows that the gate has not started."""
    monkeypatch.setattr(_gate, "GATE_START_DATE", MONDAY + timedelta(days=30))

    model = model_for(Ledger(), key_file=hmac_key)

    assert model.headline == g.NOT_STARTED
    assert model.unlocked
