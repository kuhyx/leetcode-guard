"""Remaining lock branches: the escape form's placement and the run loop."""

from __future__ import annotations

from concurrent.futures import Future
from dataclasses import replace
import logging
from typing import TYPE_CHECKING

from leetcode_guard._ledger_io import load_ledger
from leetcode_guard._netcheck import NetworkDiagnosis, NetworkVerdict
from leetcode_guard.tests._guard_factories import UNVERIFIABLE, create_guard, probe_of
from leetcode_guard.tests._ledger_fixtures import MONDAY

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


# -- outage handling -------------------------------------------------------


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
        tmp_path, probe=probe_of(), poll_probe=UNVERIFIABLE, key_file=hmac_key
    )
    guard._deps = replace(guard._deps, diagnose=diagnose)
    # Enough consecutive failures that the classifier is due to run.
    guard._poller.state.consecutive_unverifiable = 999
    return guard


def test_a_brief_blind_spell_does_not_trigger_classification(
    tmp_path: Path, hmac_key: Path
):
    """One dropped packet must not spend three TCP probes and a DNS lookup."""
    guard, _ = create_guard(
        tmp_path, probe=probe_of(), poll_probe=UNVERIFIABLE, key_file=hmac_key
    )
    calls = {"n": 0}

    def diagnose():
        calls["n"] += 1
        return local_offline()

    guard._deps = replace(guard._deps, diagnose=diagnose)
    guard._on_poll_result(UNVERIFIABLE)

    assert calls["n"] == 0
    assert guard._diagnosis is None


def test_leetcodes_own_outage_settles_the_day_and_releases(
    tmp_path: Path, hmac_key: Path
):
    """Not the user's fault and not fixable by them, so it must not cost a
    written explanation."""
    guard = blind_guard(tmp_path, hmac_key, remote_outage)

    guard._on_poll_result(UNVERIFIABLE)

    ledger = load_ledger(tmp_path / "ledger.json", key_file=hmac_key)
    charge = ledger.entries[f"charge:{MONDAY.isoformat()}"]
    assert charge.detail["source"] == "leetcode-outage"
    assert not guard._decision().locked


def test_our_own_dead_network_keeps_the_lock_shut(tmp_path: Path, hmac_key: Path):
    """The bypass this closes: unplug the cable, wait, walk away free."""
    guard = blind_guard(tmp_path, hmac_key, local_offline)

    guard._on_poll_result(UNVERIFIABLE)

    assert guard._decision().locked
    assert not (tmp_path / "ledger.json").read_text(encoding="utf-8").count("charge:")


def test_the_outage_reason_is_shown_on_the_lock(tmp_path: Path, hmac_key: Path):
    guard = blind_guard(tmp_path, hmac_key, local_offline)

    guard._on_poll_result(UNVERIFIABLE)

    assert any("no internet on this machine" in note for note in guard._model.notes)


def test_the_network_is_classified_once_not_every_tick(tmp_path: Path, hmac_key: Path):
    """Three TCP probes and a DNS lookup every 30 seconds would be noise, and
    the answer does not change between ticks."""
    calls = {"n": 0}

    def diagnose():
        calls["n"] += 1
        return local_offline()

    guard = blind_guard(tmp_path, hmac_key, diagnose)

    guard._on_poll_result(UNVERIFIABLE)
    guard._on_poll_result(UNVERIFIABLE)
    guard._on_poll_result(UNVERIFIABLE)

    assert calls["n"] == 1


def test_the_queue_wait_can_be_skipped(tmp_path: Path):
    """Only tests do this: production always queues behind higher-ranked
    lockers rather than drawing over them."""
    guard, _ = create_guard(tmp_path, wait_turn=False)

    assert guard._config.rank == 150


def test_an_outage_unlock_stops_the_poll_handler_early(tmp_path: Path, hmac_key: Path):
    """Once the outage path has released the lock, the same tick must not fall
    through and harvest against a ledger it has already settled."""
    guard = blind_guard(tmp_path, hmac_key, remote_outage)
    guard.close()

    guard._on_poll_result(UNVERIFIABLE)

    assert guard._closed


def test_a_remote_outage_with_writes_disabled_still_releases(tmp_path: Path):
    guard, _ = create_guard(
        tmp_path, probe=probe_of(), poll_probe=UNVERIFIABLE, write_ledger=False
    )
    guard._deps = replace(guard._deps, diagnose=remote_outage)
    guard._poller.state.consecutive_unverifiable = 999

    guard._on_poll_result(UNVERIFIABLE)

    assert not (tmp_path / "ledger.json").exists()


def test_production_pushes_the_ledger_on_close(tmp_path: Path, hmac_key: Path):
    """Best-effort and last, so a sync failure can never abort teardown and
    leave the screen grabbed."""
    guard, _ = create_guard(tmp_path, key_file=hmac_key)
    guard._deps = replace(guard._deps, sync_on_close=True)
    pushed = {"n": 0}

    import leetcode_guard._lock as lock_module

    original = lock_module.sync_quietly
    lock_module.sync_quietly = lambda *a, **k: pushed.__setitem__("n", pushed["n"] + 1)
    try:
        guard.on_close()
    finally:
        lock_module.sync_quietly = original

    assert pushed["n"] == 1
