"""Tests for the network-incident policy.

The asymmetry under test: a problem LeetCode caused releases the day for free,
and a problem this machine caused costs a wait plus a written account.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from gatelock import EscapeDraft

from leetcode_guard._constants import (
    NETWORK_INCIDENT_LOCKOUT_CAP_SECONDS,
    NETWORK_INCIDENT_LOCKOUT_SECONDS,
)
from leetcode_guard._netcheck import NetworkDiagnosis, NetworkVerdict
from leetcode_guard._network_incident import (
    build_tracker,
    decide_policy,
    lockout_seconds,
    record_incident,
)

if TYPE_CHECKING:
    from pathlib import Path


def diagnosis(verdict: NetworkVerdict, reason: str = "because") -> NetworkDiagnosis:
    return NetworkDiagnosis(
        verdict=verdict, reason=reason, anchors_reachable=3, addresses=("1.2.3.4",)
    )


def tracker_for(tmp_path: Path, hmac_key: Path):
    return build_tracker(tmp_path / "incidents.json", key_file=hmac_key)


def test_a_remote_outage_unlocks_with_no_form(tmp_path: Path, hmac_key: Path, caplog):
    with caplog.at_level(logging.ERROR):
        policy = decide_policy(
            diagnosis(NetworkVerdict.REMOTE_OUTAGE, "LeetCode is down"),
            tracker_for(tmp_path, hmac_key),
        )

    assert policy.unlock_now
    assert not policy.require_form
    assert policy.wait_seconds == 0
    assert "LeetCode is down" in policy.message
    assert any(record.levelno == logging.ERROR for record in caplog.records)


def test_a_local_outage_holds_and_demands_an_explanation(
    tmp_path: Path, hmac_key: Path
):
    policy = decide_policy(
        diagnosis(NetworkVerdict.LOCAL_OFFLINE, "no internet"),
        tracker_for(tmp_path, hmac_key),
    )

    assert not policy.unlock_now
    assert policy.require_form
    assert policy.wait_seconds == NETWORK_INCIDENT_LOCKOUT_SECONDS
    assert "written down what happened" in policy.message


def test_tampering_is_treated_exactly_like_being_offline(
    tmp_path: Path, hmac_key: Path
):
    """Blocking leetcode.com locally must not be softer than losing the wifi."""
    offline = decide_policy(
        diagnosis(NetworkVerdict.LOCAL_OFFLINE), tracker_for(tmp_path, hmac_key)
    )
    tampered = decide_policy(
        diagnosis(NetworkVerdict.LOCAL_TAMPERED), tracker_for(tmp_path, hmac_key)
    )

    assert tampered.unlock_now == offline.unlock_now
    assert tampered.require_form == offline.require_form
    assert tampered.wait_seconds == offline.wait_seconds


def test_being_online_neither_unlocks_nor_demands_a_form(
    tmp_path: Path, hmac_key: Path
):
    policy = decide_policy(
        diagnosis(NetworkVerdict.ONLINE), tracker_for(tmp_path, hmac_key)
    )

    assert not policy.unlock_now
    assert not policy.require_form
    assert "reachable again" in policy.message


def test_the_wait_escalates_with_repeat_incidents(tmp_path: Path, hmac_key: Path):
    tracker = tracker_for(tmp_path, hmac_key)
    first = lockout_seconds(tracker)

    tracker.record(
        EscapeDraft(
            reason="wifi died", onset="today", severity=1, description="x" * 200
        )
    )
    second = lockout_seconds(tracker)

    assert first == NETWORK_INCIDENT_LOCKOUT_SECONDS
    assert second > first


def test_the_escalating_wait_is_capped(tmp_path: Path, hmac_key: Path):
    """Uncapped doubling reaches ~2.7 hours by the sixth incident, which a
    genuinely dead ISP hits inside a week."""
    tracker = tracker_for(tmp_path, hmac_key)
    tracker.compute_lockout_seconds = lambda **_kwargs: 10**6

    assert lockout_seconds(tracker) == NETWORK_INCIDENT_LOCKOUT_CAP_SECONDS


def test_the_budget_never_exhausts(tmp_path: Path, hmac_key: Path):
    """A multi-day ISP outage must not brick the machine."""
    tracker = tracker_for(tmp_path, hmac_key)
    for index in range(12):
        tracker.record(
            EscapeDraft(
                reason=f"outage {index}",
                onset="today",
                severity=1,
                description="y" * 200,
            )
        )

    assert not tracker.is_budget_exhausted()


def test_a_short_explanation_is_refused(tmp_path: Path, hmac_key: Path):
    tracker = tracker_for(tmp_path, hmac_key)
    draft = EscapeDraft(reason="wifi", onset="now", severity=1, description="short")

    complaint = record_incident(tracker, draft, diagnosis(NetworkVerdict.LOCAL_OFFLINE))

    assert complaint is not None
    assert "characters" in complaint


def test_a_blank_onset_is_refused(tmp_path: Path, hmac_key: Path):
    tracker = tracker_for(tmp_path, hmac_key)
    draft = EscapeDraft(reason="wifi", onset="", severity=1, description="z" * 200)

    assert record_incident(tracker, draft, diagnosis(NetworkVerdict.LOCAL_OFFLINE))


def test_a_complete_explanation_is_accepted_and_recorded(
    tmp_path: Path, hmac_key: Path, caplog
):
    tracker = tracker_for(tmp_path, hmac_key)
    draft = EscapeDraft(
        reason="the router died", onset="08:15", severity=1, description="z" * 200
    )

    with caplog.at_level(logging.WARNING):
        complaint = record_incident(
            tracker, draft, diagnosis(NetworkVerdict.LOCAL_OFFLINE)
        )

    assert complaint is None
    assert tracker.count_in_window(7) == 1
    assert any("network incident recorded" in r.message for r in caplog.records)


def test_a_failed_save_is_reported_not_silently_accepted(
    tmp_path: Path, hmac_key: Path
):
    tracker = tracker_for(tmp_path, hmac_key)
    tracker.record = lambda *_a, **_k: False
    draft = EscapeDraft(reason="r", onset="o", severity=1, description="z" * 200)

    complaint = record_incident(tracker, draft, diagnosis(NetworkVerdict.LOCAL_OFFLINE))

    assert complaint is not None
    assert "try again" in complaint


def test_incidents_are_kept_apart_from_the_ordinary_escape_budget(
    tmp_path: Path, hmac_key: Path
):
    """A week of bad wifi must not consume the allowance meant for "I genuinely
    cannot do this today"."""
    from leetcode_guard._escape_flow import build_tracker as build_escape_tracker

    incidents = tracker_for(tmp_path, hmac_key)
    escapes = build_escape_tracker(tmp_path / "escape.json", key_file=hmac_key)
    incidents.record(
        EscapeDraft(reason="wifi", onset="now", severity=1, description="q" * 200)
    )

    assert incidents.count_in_window(7) == 1
    assert escapes.count_in_window(7) == 0
    assert not escapes.is_budget_exhausted()
