"""End-to-end ledger stories, asserted against the user's own words.

The specification was: "if on monday I do 3 questions, unlock on monday (duh),
and on tuesday and wednesday and then lock again on thursday". That sentence is
:func:`test_three_solves_on_monday_unlock_monday_tuesday_wednesday_then_lock`,
literally. If that test ever needs adjusting, the feature has changed.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from leetcode_guard._gate import GateState, apply_decision, decide
from leetcode_guard._harvest import commit_harvest, harvest, needs_seeding, seed_ledger
from leetcode_guard._ledger_io import Ledger, load_ledger
from leetcode_guard._submissions import ProbeStatus, SolveProbe
from leetcode_guard.tests._guard_factories import create_guard, probe_of
from leetcode_guard.tests._ledger_fixtures import (
    FRIDAY,
    MONDAY,
    NOW,
    SATURDAY,
    SUNDAY,
    THURSDAY,
    TUESDAY,
    WEDNESDAY,
    ledger_with_credits,
    submission,
)

if TYPE_CHECKING:
    from pathlib import Path


def run_day(ledger: Ledger, day: date, path: Path, key_file: Path) -> GateState:
    """Fire the gate for one day, persisting whatever it decides."""
    decision = decide(ledger, day=day, now=NOW, key_file=key_file)
    apply_decision(ledger, decision, path)
    return decision.state


def test_three_solves_on_monday_unlock_monday_tuesday_wednesday_then_lock(
    tmp_path: Path, hmac_key: Path
):
    path = tmp_path / "ledger.json"
    ledger = ledger_with_credits(3, day=MONDAY, key_file=hmac_key)

    assert run_day(ledger, MONDAY, path, hmac_key) is GateState.UNLOCKED_CHARGED_NOW
    assert run_day(ledger, TUESDAY, path, hmac_key) is GateState.UNLOCKED_CHARGED_NOW
    assert run_day(ledger, WEDNESDAY, path, hmac_key) is GateState.UNLOCKED_CHARGED_NOW
    assert run_day(ledger, THURSDAY, path, hmac_key) is GateState.LOCKED_INSUFFICIENT

    thursday = decide(ledger, day=THURSDAY, now=NOW, key_file=hmac_key)
    assert thursday.needed == 1
    assert thursday.balance.available == 0


def test_a_weekend_day_costs_two_credits(tmp_path: Path, hmac_key: Path):
    path = tmp_path / "ledger.json"
    ledger = ledger_with_credits(2, day=FRIDAY, key_file=hmac_key)

    assert run_day(ledger, SATURDAY, path, hmac_key) is GateState.UNLOCKED_CHARGED_NOW
    assert decide(ledger, day=SUNDAY, now=NOW, key_file=hmac_key).balance.available == 0
    assert run_day(ledger, SUNDAY, path, hmac_key) is GateState.LOCKED_INSUFFICIENT


def test_one_credit_is_not_enough_for_a_weekend_day(tmp_path: Path, hmac_key: Path):
    ledger = ledger_with_credits(1, day=FRIDAY, key_file=hmac_key)

    decision = decide(ledger, day=SATURDAY, now=NOW, key_file=hmac_key)

    assert decision.state is GateState.LOCKED_INSUFFICIENT
    assert decision.cost == 2
    assert decision.needed == 1


def test_weekday_credits_are_spendable_on_a_weekend(tmp_path: Path, hmac_key: Path):
    """Credits are fungible; the weekend just consumes them twice as fast."""
    path = tmp_path / "ledger.json"
    ledger = ledger_with_credits(4, day=MONDAY, key_file=hmac_key)

    assert run_day(ledger, SATURDAY, path, hmac_key) is GateState.UNLOCKED_CHARGED_NOW
    assert run_day(ledger, SUNDAY, path, hmac_key) is GateState.UNLOCKED_CHARGED_NOW
    assert decide(ledger, day=MONDAY, now=NOW, key_file=hmac_key).balance.available == 0


def test_there_is_no_cap_on_banked_credits(tmp_path: Path, hmac_key: Path):
    """Explicitly chosen: thirty solves bank thirty credits."""
    ledger = ledger_with_credits(30, day=MONDAY, key_file=hmac_key)

    assert (
        decide(ledger, day=MONDAY, now=NOW, key_file=hmac_key).balance.available == 30
    )


def test_days_the_pc_was_off_are_never_charged(tmp_path: Path, hmac_key: Path):
    """Charge on use, never retroactively. Coming back from a fortnight away
    must not present a bill for fourteen days."""
    path = tmp_path / "ledger.json"
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    run_day(ledger, MONDAY, path, hmac_key)

    far_later = date(2026, 8, 20)
    decision = decide(ledger, day=far_later, now=NOW, key_file=hmac_key)

    assert decision.balance.charged == 1
    assert decision.state is GateState.LOCKED_INSUFFICIENT
    assert decision.needed == 1


def test_rerunning_the_same_day_is_a_no_op(tmp_path: Path, hmac_key: Path):
    """What makes the afternoon retry safe."""
    path = tmp_path / "ledger.json"
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)

    assert run_day(ledger, MONDAY, path, hmac_key) is GateState.UNLOCKED_CHARGED_NOW
    assert run_day(ledger, MONDAY, path, hmac_key) is GateState.UNLOCKED_ALREADY_CHARGED
    assert decide(ledger, day=MONDAY, now=NOW, key_file=hmac_key).balance.charged == 1


def test_first_run_seeds_without_touching_the_gate(tmp_path: Path, hmac_key: Path):
    """Without seeding, run one would mint the whole recent feed as credits and
    the gate would never gate.

    Seeding leaves the gate itself untouched: no charge, no credit. Deferring
    the first arm is the *run's* job (``cmd_lock`` returns early), because a
    deferral written into the ledger is a deferral the gate honours -- and
    ``charge:<today>`` is exactly the key ``decide`` unlocks on, so writing one
    turned ``rm ledger.json`` into a free day.
    """
    path = tmp_path / "ledger.json"
    ledger = Ledger()
    old = SolveProbe(
        status=ProbeStatus.OK,
        submissions=tuple(submission(f"old-{index}") for index in range(20)),
        reason="20 recent",
    )

    assert needs_seeding(ledger)
    assert (
        seed_ledger(ledger, old, day=MONDAY, now=NOW, path=path, key_file=hmac_key)
        == 20
    )
    assert not needs_seeding(ledger)

    assert harvest(ledger, old, day=MONDAY, now=NOW, key_file=hmac_key).gained == 0
    # The gate is untouched by seeding: still locked, balance still zero.
    assert decide(ledger, day=MONDAY, now=NOW, key_file=hmac_key).state is (
        GateState.LOCKED_INSUFFICIENT
    )
    assert decide(ledger, day=MONDAY, now=NOW, key_file=hmac_key).balance.available == 0

    fresh = SolveProbe(
        status=ProbeStatus.OK,
        submissions=(submission("brand-new"), *old.submissions),
        reason="21 recent",
    )
    result = harvest(ledger, fresh, day=MONDAY, now=NOW, key_file=hmac_key)
    commit_harvest(ledger, result, path)

    assert result.gained == 1
    assert result.already_known == 20
    # One fresh solve, one unlocked day. No debt to work off first.
    assert decide(ledger, day=MONDAY, now=NOW, key_file=hmac_key).state is (
        GateState.UNLOCKED_CHARGED_NOW
    )


def test_seeding_never_writes_a_credit(tmp_path: Path, hmac_key: Path):
    """The deferral must not become a bypass. A credit exists only because
    LeetCode confirmed an accepted submission; hand-writing one to make day one
    pleasant is exactly the asymmetry ``_balance`` was built to refuse."""
    path = tmp_path / "ledger.json"
    ledger = Ledger()
    probe = SolveProbe(
        status=ProbeStatus.OK,
        submissions=tuple(submission(f"old-{index}") for index in range(5)),
        reason="5 recent",
    )

    seed_ledger(ledger, probe, day=MONDAY, now=NOW, path=path, key_file=hmac_key)

    kinds = {entry.kind for entry in ledger.entries.values()}
    assert "credit" not in kinds
    # No charge either: a charge for today is the key `decide` unlocks on, so
    # writing one here turned `rm ledger.json` into a free day.
    assert kinds == {"seen", "bootstrap"}


def test_an_unverifiable_first_probe_settles_nothing(tmp_path: Path, hmac_key: Path):
    """Unplugging the ethernet before the first run must not buy a free day."""
    path = tmp_path / "ledger.json"
    ledger = Ledger()
    blind = SolveProbe(
        status=ProbeStatus.UNVERIFIABLE, submissions=(), reason="cannot reach LeetCode"
    )

    assert (
        seed_ledger(ledger, blind, day=MONDAY, now=NOW, path=path, key_file=hmac_key)
        == -1
    )

    assert ledger.entries == {}
    assert needs_seeding(ledger)


def test_an_already_seeded_ledger_is_never_rewritten(tmp_path: Path, hmac_key: Path):
    """The deferral applies to ledgers this code creates. One that already
    exists -- including the one seeded during the incident -- keeps whatever it
    already says."""
    path = tmp_path / "ledger.json"
    ledger = Ledger()
    probe = SolveProbe(
        status=ProbeStatus.OK, submissions=(submission("old-1"),), reason="1 recent"
    )
    seed_ledger(ledger, probe, day=MONDAY, now=NOW, path=path, key_file=hmac_key)
    before = path.read_bytes()

    assert not needs_seeding(ledger)

    assert path.read_bytes() == before


def test_a_freshly_seeded_lock_offers_a_way_out_at_t0(
    tmp_path: Path, hmac_key: Path, tk_mock
):
    """The 2026-08-05 incident, as an assertion.

    That morning every exit closed at once: the gate demanded a *fresh* solve,
    the problems rendered as inert text with no way to open one, the package
    could not launch a browser at all, and the hatch was gated behind ten
    minutes so it had not appeared yet. The machine was fully grabbed. The user
    escaped only because a terminal happened to already be open.

    Whatever else changes, at least one exit must be open from the first
    second. This test fails against the code as it stood that morning.
    """
    # An already-seeded ledger with nothing banked: the ordinary locked day,
    # and the state the machine was actually in that morning. Seeding now
    # defers its own day, so a *fresh* ledger would not arm at all.
    path = tmp_path / "ledger.json"
    ledger = Ledger()
    seed_ledger(
        ledger,
        probe_of("old-1", "old-2"),
        day=MONDAY,
        now=NOW,
        path=path,
        key_file=hmac_key,
    )
    guard, _ = create_guard(
        tmp_path,
        probe=probe_of("old-1", "old-2"),
        key_file=hmac_key,
        now=datetime.combine(TUESDAY, NOW.timetz()),
    )

    assert guard._decision().locked, "this scenario has to be a locked gate"
    assert guard._model.problems, "a lock that names no problem cannot be satisfied"

    opens = [
        call
        for call in tk_mock.Button.call_args_list
        if call.kwargs.get("text") == "Open"
    ]
    assert len(opens) == len(guard._model.problems), (
        "every listed problem needs a control that opens it -- naming a problem "
        "the user cannot reach is what made the lock unsatisfiable"
    )

    assert guard._should_offer_escape(), (
        "the hatch must be reachable at t=0; one that appears after ten minutes "
        "is not a safety valve during those ten minutes"
    )


def test_a_solve_from_before_the_lock_engaged_still_counts(
    tmp_path: Path, hmac_key: Path
):
    """Dedupe is by submission id, not by a launch-time window, so an early
    morning solve is not wasted."""
    path = tmp_path / "ledger.json"
    ledger = Ledger()
    seed_ledger(
        ledger,
        SolveProbe(status=ProbeStatus.OK, submissions=(), reason="none"),
        day=MONDAY,
        now=NOW,
        path=path,
        key_file=hmac_key,
    )
    early = SolveProbe(
        status=ProbeStatus.OK,
        submissions=(submission("solved-at-dawn"),),
        reason="1 recent",
    )

    result = harvest(ledger, early, day=MONDAY, now=NOW, key_file=hmac_key)

    assert result.gained == 1


def test_harvesting_twice_mints_nothing_the_second_time(tmp_path: Path, hmac_key: Path):
    """Polling every 30 seconds must be idempotent."""
    path = tmp_path / "ledger.json"
    ledger = Ledger()
    probe = SolveProbe(
        status=ProbeStatus.OK, submissions=(submission("one"),), reason="1 recent"
    )

    first = harvest(ledger, probe, day=MONDAY, now=NOW, key_file=hmac_key)
    commit_harvest(ledger, first, path)
    second = harvest(ledger, probe, day=MONDAY, now=NOW, key_file=hmac_key)

    assert first.gained == 1
    assert second.gained == 0
    assert second.already_known == 1


def test_the_ledger_survives_a_round_trip_through_disk(tmp_path: Path, hmac_key: Path):
    path = tmp_path / "ledger.json"
    ledger = ledger_with_credits(3, day=MONDAY, key_file=hmac_key)
    run_day(ledger, MONDAY, path, hmac_key)

    reloaded = load_ledger(path, key_file=hmac_key)
    decision = decide(reloaded, day=TUESDAY, now=NOW, key_file=hmac_key)

    assert reloaded.tampered == 0
    assert reloaded.integrity_ok
    assert decision.balance.credits == 3
    assert decision.balance.available == 2
    assert decision.state is GateState.UNLOCKED_CHARGED_NOW
