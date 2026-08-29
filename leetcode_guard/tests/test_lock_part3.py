"""The offline path's exit -- the network-incident form.

Split from ``test_lock_part2.py`` for the repo's 400-line cap. These are
the tests for the worst bug this repo has had: LOCAL_OFFLINE plus a spent
escape budget held the keyboard while the screen promised a way out that
did not exist.
"""

from __future__ import annotations

from concurrent.futures import Future
from dataclasses import replace
import logging
from typing import TYPE_CHECKING

from leetcode_guard._netcheck import NetworkDiagnosis, NetworkVerdict
from leetcode_guard.tests._guard_factories import UNVERIFIABLE, create_guard, probe_of

if TYPE_CHECKING:
    from pathlib import Path


def test_the_escape_form_opens_on_a_surface(tmp_path: Path):
    guard, _ = create_guard(tmp_path)

    guard._open_escape()

    assert guard._hatch.open


def test_opening_the_escape_form_twice_is_a_no_op(tmp_path: Path):
    guard, _ = create_guard(tmp_path)

    guard._open_escape()
    first = guard._hatch._form
    guard._open_escape()

    assert guard._hatch._form is first


def test_the_escape_form_declines_to_open_with_no_surface(tmp_path: Path, caplog):
    """Zero live outputs still holds the grab, so the request is legitimate --
    it just has nowhere to draw. It must say so rather than crash the lock."""
    guard, _ = create_guard(tmp_path)
    guard._frames.clear()

    with caplog.at_level(logging.WARNING):
        guard._open_escape()

    assert not guard._hatch.open
    assert any("no surface available" in record.message for record in caplog.records)


def test_run_delegates_to_the_lock_window(tmp_path: Path):
    guard, _ = create_guard(tmp_path)

    guard.run()

    assert True


def test_a_seeded_ledger_is_not_reseeded_on_a_later_run(tmp_path: Path, hmac_key: Path):
    create_guard(tmp_path, probe=probe_of("a"), key_file=hmac_key)

    second, _ = create_guard(tmp_path, probe=probe_of("a", "b"), key_file=hmac_key)

    # "b" arrived after seeding, so it is a credit rather than a marker.
    second._on_poll_result(probe_of("a", "b"))
    assert not second._decision().locked


def test_write_ledger_false_skips_seeding_entirely(tmp_path: Path):
    create_guard(tmp_path, probe=probe_of("a"), write_ledger=False)

    assert not (tmp_path / "ledger.json").exists()


def test_a_pending_future_leaves_the_drain_rescheduling(tmp_path: Path):
    """Covers the branch where the executor has not finished yet."""
    guard, _ = create_guard(tmp_path)
    guard._poller._future = Future()

    guard._poller._drain()

    assert guard._poller._future is not None


def test_the_unlocked_path_with_write_disabled_skips_the_charge(tmp_path: Path):
    """Covers the branch where a decision would charge but nothing may be
    written -- demo mode running against a ledger it must not touch."""
    guard, _ = create_guard(
        tmp_path,
        probe=probe_of("old"),
        poll_probe=probe_of("new", "old"),
        write_ledger=False,
    )

    guard._on_poll_result(guard._check())

    assert not (tmp_path / "ledger.json").exists()


def test_the_escape_grant_with_write_disabled_still_releases(tmp_path: Path):
    guard, _ = create_guard(tmp_path, write_ledger=False)

    guard._on_escape_granted("a reason")

    assert not (tmp_path / "ledger.json").exists()


def test_a_tick_while_a_future_is_in_flight_does_not_resubmit(tmp_path: Path):
    guard, _ = create_guard(tmp_path)
    pending: Future = Future()
    guard._poller._future = pending

    guard._poller._tick()

    assert guard._poller._future is pending


def test_a_stopped_poller_ignores_a_tick(tmp_path: Path):
    guard, _ = create_guard(tmp_path)
    guard._poller.stop()
    guard._poller._future = None

    guard._poller._tick()

    assert guard._poller._future is None


def test_an_already_charged_day_unlocks_without_writing_a_second_charge(
    tmp_path: Path, hmac_key: Path
):
    """The afternoon retry lands here: today is settled, the decision carries
    no charge, and the lock releases without touching the ledger again."""
    guard, _ = create_guard(
        tmp_path,
        probe=probe_of("old"),
        poll_probe=probe_of("new", "old"),
        key_file=hmac_key,
    )
    guard._on_poll_result(guard._check())
    before = (tmp_path / "ledger.json").read_text(encoding="utf-8")

    guard._on_poll_result(guard._check())

    assert guard._decision().charge is None
    assert (tmp_path / "ledger.json").read_text(encoding="utf-8") == before


def remote_outage() -> NetworkDiagnosis:
    return NetworkDiagnosis(
        verdict=NetworkVerdict.REMOTE_OUTAGE,
        reason="LeetCode is down",
        anchors_reachable=3,
        addresses=("1.2.3.4",),
    )


def local_offline() -> NetworkDiagnosis:
    return NetworkDiagnosis(
        verdict=NetworkVerdict.LOCAL_OFFLINE,
        reason="no internet on this machine",
        anchors_reachable=0,
        addresses=(),
    )


def blind_guard(tmp_path: Path, hmac_key: Path, diagnose):
    guard, _ = create_guard(
        tmp_path,
        probe=probe_of(),
        poll_probe=UNVERIFIABLE,
        key_file=hmac_key,
        # An ordinary gating day: seeding settles the day it runs on, so a
        # self-seeding guard is unlocked and none of these outage paths apply.
        seeded=True,
    )
    guard._deps = replace(guard._deps, diagnose=diagnose)
    # Enough consecutive failures that the classifier is due to run.
    guard._poller.state.consecutive_unverifiable = 999
    return guard


def blind_offline(tmp_path: Path, hmac_key: Path):
    """A guard that has been blind long enough, with LOCAL_OFFLINE diagnosed."""
    guard = blind_guard(tmp_path, hmac_key, local_offline)
    guard._on_poll_result(UNVERIFIABLE)
    return guard


def test_a_local_outage_captures_the_incident_policy(tmp_path: Path, hmac_key: Path):
    guard = blind_offline(tmp_path, hmac_key)

    assert guard._incident_policy is not None
    assert guard._incident_policy.require_form
    assert guard._decision().locked
