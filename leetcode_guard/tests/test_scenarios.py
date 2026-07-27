"""End-to-end ledger stories, asserted against the user's own words.

The specification was: "if on monday I do 3 questions, unlock on monday (duh),
and on tuesday and wednesday and then lock again on thursday". That sentence is
:func:`test_three_solves_on_monday_unlock_monday_tuesday_wednesday_then_lock`,
literally. If that test ever needs adjusting, the feature has changed.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from leetcode_guard._gate import GateState, apply_decision, decide
from leetcode_guard._harvest import commit_harvest, harvest, needs_seeding, seed_ledger
from leetcode_guard._ledger_io import Ledger, load_ledger
from leetcode_guard._submissions import ProbeStatus, SolveProbe
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


def test_first_run_seeds_and_still_demands_a_fresh_solve(
    tmp_path: Path, hmac_key: Path
):
    """Without seeding, run one would mint the whole recent feed as credits and
    the gate would never gate."""
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
    assert decide(ledger, day=MONDAY, now=NOW, key_file=hmac_key).state is (
        GateState.LOCKED_INSUFFICIENT
    )

    fresh = SolveProbe(
        status=ProbeStatus.OK,
        submissions=(submission("brand-new"), *old.submissions),
        reason="21 recent",
    )
    result = harvest(ledger, fresh, day=MONDAY, now=NOW, key_file=hmac_key)
    commit_harvest(ledger, result, path)

    assert result.gained == 1
    assert result.already_known == 20
    assert decide(ledger, day=MONDAY, now=NOW, key_file=hmac_key).state is (
        GateState.UNLOCKED_CHARGED_NOW
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
