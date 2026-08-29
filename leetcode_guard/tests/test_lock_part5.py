"""Continued from :mod:`leetcode_guard.tests.test_lock_part2`, split for the 250-line cap."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from leetcode_guard._ledger_io import load_ledger
from leetcode_guard.tests._guard_factories import UNVERIFIABLE, create_guard, probe_of
from leetcode_guard.tests._ledger_fixtures import MONDAY

if TYPE_CHECKING:
    from pathlib import Path


from leetcode_guard.tests.test_lock_part2 import (
    blind_guard,
    local_offline,
    remote_outage,
)


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
    # No charge for *today*. The seeding run settled its own day (an earlier
    # one), and that entry is not what this test is about.
    assert f"charge:{MONDAY.isoformat()}" not in (
        (tmp_path / "ledger.json").read_text(encoding="utf-8")
    )


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
