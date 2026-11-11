"""Continued from :mod:`leetcode_guard.tests.test_lock_part3`, split for the 250-line cap."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from gatelock import EscapeDraft

from leetcode_guard._escape_flow import build_tracker
from leetcode_guard._netcheck import NetworkDiagnosis, NetworkVerdict
from leetcode_guard.tests._blind_fixtures import (
    blind_guard,
    blind_offline,
)
from leetcode_guard.tests._guard_factories import UNVERIFIABLE, create_guard, probe_of
from leetcode_guard.tests._ledger_fixtures import MONDAY

if TYPE_CHECKING:
    from pathlib import Path


def test_the_incident_form_is_not_offered_before_its_wait(
    tmp_path: Path, hmac_key: Path
):
    """The ordinary hatch is still offered here -- a blind gate reveals it
    after three minutes -- so what must NOT be available yet is the incident
    form, which costs no budget."""
    guard = blind_offline(tmp_path, hmac_key)

    assert not guard.incident_form_due()

    guard.open_escape()

    assert guard.escape.hatch.open
    assert not guard.escape.incident_hatch.open


def test_the_incident_form_is_offered_once_the_wait_elapses(
    tmp_path: Path, hmac_key: Path
):
    """Once the offline wait has elapsed, the incident form is due and offered."""
    guard = blind_offline(tmp_path, hmac_key)
    guard.outage.since = time.monotonic() - 10_000

    assert guard.incident_form_due()
    assert guard.should_offer_escape()


def test_the_offline_path_has_an_exit_even_with_the_escape_budget_spent(
    tmp_path: Path, hmac_key: Path
):
    """The bug this closes: LOCAL_OFFLINE plus a spent escape budget left the
    lock holding the keyboard while promising on screen that writing down what
    happened would release it. There was no form to write it in."""
    spent = build_tracker(tmp_path / "escape.json", key_file=hmac_key)
    spent.record(
        EscapeDraft(reason="used", onset="y", severity=1, description="x" * 200)
    )

    guard = blind_offline(tmp_path, hmac_key)
    guard.outage.since = time.monotonic() - 10_000

    assert guard.escape.tracker.is_budget_exhausted()
    assert guard.should_offer_escape()

    guard.open_escape()
    assert guard.escape.incident_hatch.open
    assert not guard.escape.hatch.open

    form = guard.escape.incident_hatch.form
    form.reason.get.return_value = "the router died and the ISP is down"
    form.description.get.return_value = "y" * 200

    assert guard.escape.incident_hatch.submit()
    assert not guard.decision().locked


def test_an_incident_unlock_is_tagged_apart_from_an_escape(
    tmp_path: Path, hmac_key: Path
):
    """So a week of bad wifi is distinguishable in the ledger from "I could not
    face it today", and does not consume the escape budget."""
    guard = blind_offline(tmp_path, hmac_key)

    guard.on_incident_recorded("the router died")

    charge = guard.ledger.entries[f"charge:{MONDAY.isoformat()}"]
    assert charge.detail["source"] == "network-incident"


def test_the_ordinary_hatch_is_used_when_the_gate_is_not_offline(
    tmp_path: Path, hmac_key: Path
):
    """Without an offline diagnosis, escaping opens the ordinary hatch only."""
    guard, _ = create_guard(tmp_path, key_file=hmac_key)

    guard.open_escape()

    assert guard.escape.hatch.open
    assert not guard.escape.incident_hatch.open


def test_opening_a_form_twice_is_a_no_op(tmp_path: Path, hmac_key: Path):
    """A second open keeps the same incident form instead of building a new one."""
    guard = blind_offline(tmp_path, hmac_key)
    guard.outage.since = time.monotonic() - 10_000
    guard.open_escape()
    first = guard.escape.incident_hatch.form

    guard.open_escape()

    assert guard.escape.incident_hatch.form is first


def test_a_recovered_network_clears_the_stale_banner(tmp_path: Path, hmac_key: Path):
    """The banner outlived the outage, telling the user they had no internet
    long after they had reconnected."""
    guard = blind_offline(tmp_path, hmac_key)
    assert guard.outage.note is not None

    guard.on_poll_result(probe_of("solved-after-reconnect"))

    assert guard.outage.diagnosis is None
    assert guard.outage.note is None
    assert guard.outage.policy is None


def test_clearing_an_outage_that_never_happened_is_a_no_op(
    tmp_path: Path, hmac_key: Path
):
    """Clearing with no outage recorded leaves the outage state empty."""
    guard, _ = create_guard(tmp_path, key_file=hmac_key)

    guard.clear_outage()

    assert guard.outage.diagnosis is None


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

    guard.on_poll_result(UNVERIFIABLE)

    assert guard.decision().locked
    assert guard.outage.policy is None
    assert not guard.incident_form_due()
