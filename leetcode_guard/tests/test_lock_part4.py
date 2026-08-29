"""Continued from :mod:`leetcode_guard.tests.test_lock_part3`, split for the 250-line cap."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from leetcode_guard._netcheck import NetworkDiagnosis, NetworkVerdict
from leetcode_guard.tests._guard_factories import UNVERIFIABLE, create_guard, probe_of
from leetcode_guard.tests._ledger_fixtures import MONDAY

if TYPE_CHECKING:
    from pathlib import Path


from leetcode_guard.tests.test_lock_part3 import (
    blind_guard,
    blind_offline,
)


def test_the_incident_form_is_not_offered_before_its_wait(
    tmp_path: Path, hmac_key: Path
):
    """The ordinary hatch is still offered here -- a blind gate reveals it
    after three minutes -- so what must NOT be available yet is the incident
    form, which costs no budget."""
    guard = blind_offline(tmp_path, hmac_key)

    assert not guard._incident_form_due()

    guard._open_escape()

    assert guard._hatch.open
    assert not guard._incident_hatch.open


def test_the_incident_form_is_offered_once_the_wait_elapses(
    tmp_path: Path, hmac_key: Path
):
    guard = blind_offline(tmp_path, hmac_key)
    guard._outage_since = time.monotonic() - 10_000

    assert guard._incident_form_due()
    assert guard._should_offer_escape()


def test_the_offline_path_has_an_exit_even_with_the_escape_budget_spent(
    tmp_path: Path, hmac_key: Path
):
    """The bug this closes: LOCAL_OFFLINE plus a spent escape budget left the
    lock holding the keyboard while promising on screen that writing down what
    happened would release it. There was no form to write it in."""
    from gatelock import EscapeDraft

    from leetcode_guard._escape_flow import build_tracker

    spent = build_tracker(tmp_path / "escape.json", key_file=hmac_key)
    spent.record(
        EscapeDraft(reason="used", onset="y", severity=1, description="x" * 200)
    )

    guard = blind_offline(tmp_path, hmac_key)
    guard._outage_since = time.monotonic() - 10_000

    assert guard._tracker.is_budget_exhausted()
    assert guard._should_offer_escape()

    guard._open_escape()
    assert guard._incident_hatch.open
    assert not guard._hatch.open

    form = guard._incident_hatch._form
    form.reason.get.return_value = "the router died and the ISP is down"
    form.description.get.return_value = "y" * 200

    assert guard._incident_hatch.submit()
    assert not guard._decision().locked


def test_an_incident_unlock_is_tagged_apart_from_an_escape(
    tmp_path: Path, hmac_key: Path
):
    """So a week of bad wifi is distinguishable in the ledger from "I could not
    face it today", and does not consume the escape budget."""
    guard = blind_offline(tmp_path, hmac_key)

    guard._on_incident_recorded("the router died")

    charge = guard._ledger.entries[f"charge:{MONDAY.isoformat()}"]
    assert charge.detail["source"] == "network-incident"


def test_the_ordinary_hatch_is_used_when_the_gate_is_not_offline(
    tmp_path: Path, hmac_key: Path
):
    guard, _ = create_guard(tmp_path, key_file=hmac_key)

    guard._open_escape()

    assert guard._hatch.open
    assert not guard._incident_hatch.open


def test_opening_a_form_twice_is_a_no_op(tmp_path: Path, hmac_key: Path):
    guard = blind_offline(tmp_path, hmac_key)
    guard._outage_since = time.monotonic() - 10_000
    guard._open_escape()
    first = guard._incident_hatch._form

    guard._open_escape()

    assert guard._incident_hatch._form is first


def test_a_recovered_network_clears_the_stale_banner(tmp_path: Path, hmac_key: Path):
    """The banner outlived the outage, telling the user they had no internet
    long after they had reconnected."""
    guard = blind_offline(tmp_path, hmac_key)
    assert guard._outage_note is not None

    guard._on_poll_result(probe_of("solved-after-reconnect"))

    assert guard._diagnosis is None
    assert guard._outage_note is None
    assert guard._incident_policy is None


def test_clearing_an_outage_that_never_happened_is_a_no_op(
    tmp_path: Path, hmac_key: Path
):
    guard, _ = create_guard(tmp_path, key_file=hmac_key)

    guard.clear_outage()

    assert guard._diagnosis is None


def test_a_recovered_leetcode_neither_unlocks_nor_demands_a_form(
    tmp_path: Path, hmac_key: Path
):
    """ONLINE means the probe failures were transient. Keep watching -- do not
    hand out a day, and do not make them justify anything."""
    online = NetworkDiagnosis(
        verdict=NetworkVerdict.ONLINE,
        reason="LeetCode answered a direct probe",
        anchors_reachable=3,
        addresses=("1.2.3.4",),
    )
    guard = blind_guard(tmp_path, hmac_key, lambda: online)

    guard._on_poll_result(UNVERIFIABLE)

    assert guard._decision().locked
    assert guard._incident_policy is None
    assert not guard._incident_form_due()
