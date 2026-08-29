"""Continued from :mod:`leetcode_guard.tests.test_scenarios`, split for the 250-line cap."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from leetcode_guard._gate import GateState, decide
from leetcode_guard._harvest import commit_harvest, harvest, needs_seeding, seed_ledger
from leetcode_guard._ledger_io import Ledger, load_ledger
from leetcode_guard._submissions import ProbeStatus, SolveProbe
from leetcode_guard.tests._guard_factories import create_guard, probe_of
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    NOW,
    TUESDAY,
    ledger_with_credits,
    submission,
)

if TYPE_CHECKING:
    from pathlib import Path


from leetcode_guard.tests.test_scenarios import (
    run_day,
)


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
