"""Tests for network-failure classification.

The table below is the anti-bypass surface. Getting a row wrong either hands
out free unlocks (classifying a local block as a remote outage) or punishes the
user for LeetCode's downtime.
"""

from __future__ import annotations

import logging

import pytest

from leetcode_guard._netcheck import (
    ANCHORS,
    LEETCODE_HOST,
    NetworkVerdict,
    classify,
    resolve_host,
    tcp_reachable,
)

PUBLIC = ("104.16.1.1",)


def all_reachable(_host: str, _port: int) -> bool:
    return True


def none_reachable(_host: str, _port: int) -> bool:
    return False


def test_a_dead_connection_is_our_problem():
    """Unplugging the ethernet must not read as "LeetCode is down"."""
    diagnosis = classify(connect=none_reachable, resolve=lambda _h: PUBLIC)

    assert diagnosis.verdict is NetworkVerdict.LOCAL_OFFLINE
    assert diagnosis.verdict.is_our_fault
    assert not diagnosis.unlocks
    assert diagnosis.anchors_reachable == 0


def test_a_working_connection_with_a_dead_leetcode_is_a_remote_outage():
    diagnosis = classify(
        connect=all_reachable, resolve=lambda _h: PUBLIC, identity_ok=lambda: False
    )

    assert diagnosis.verdict is NetworkVerdict.REMOTE_OUTAGE
    assert diagnosis.unlocks
    assert not diagnosis.verdict.is_our_fault
    assert diagnosis.anchors_reachable == len(ANCHORS)


def test_a_leetcode_that_answers_is_online_and_must_not_unlock():
    """The bypass this closes: without it, any transient blip lasting longer
    than the blind threshold handed out a free day while LeetCode was fine."""
    diagnosis = classify(
        connect=all_reachable, resolve=lambda _h: PUBLIC, identity_ok=lambda: True
    )

    assert diagnosis.verdict is NetworkVerdict.ONLINE
    assert not diagnosis.unlocks
    assert not diagnosis.verdict.is_our_fault


def test_one_reachable_anchor_is_enough_to_prove_we_are_online():
    """Anchors are independent; a single responder rules out "no internet"."""
    calls = {"n": 0}

    def one_works(_host: str, _port: int) -> bool:
        calls["n"] += 1
        return calls["n"] == 1

    diagnosis = classify(
        connect=one_works, resolve=lambda _h: PUBLIC, identity_ok=lambda: False
    )

    assert diagnosis.verdict is NetworkVerdict.REMOTE_OUTAGE
    assert diagnosis.anchors_reachable == 1


@pytest.mark.parametrize(
    "addresses",
    [("127.0.0.1",), ("0.0.0.0",), ("192.168.1.5",), ("10.0.0.1",), ("172.16.0.9",)],
)
def test_a_locally_answered_name_is_tampering_not_an_outage(addresses, caplog):
    """The /etc/hosts hole: one line would otherwise buy a free unlock daily."""
    with caplog.at_level(logging.ERROR):
        diagnosis = classify(connect=all_reachable, resolve=lambda _h: addresses)

    assert diagnosis.verdict is NetworkVerdict.LOCAL_TAMPERED
    assert diagnosis.verdict.is_our_fault
    assert not diagnosis.unlocks
    assert any(record.levelno == logging.ERROR for record in caplog.records)


def test_a_name_that_does_not_resolve_at_all_is_tampering():
    diagnosis = classify(connect=all_reachable, resolve=lambda _h: ())

    assert diagnosis.verdict is NetworkVerdict.LOCAL_TAMPERED
    assert "does not resolve" in diagnosis.reason


def test_a_portal_on_a_public_address_is_an_acknowledged_gap():
    """Documented honestly rather than papered over: a portal answering from a
    public IP is indistinguishable from a real outage here, and unlocks. The
    DNS checks catch the cheap local blocks; this one is not caught."""
    diagnosis = classify(
        connect=all_reachable, resolve=lambda _h: PUBLIC, identity_ok=lambda: False
    )

    assert diagnosis.verdict is NetworkVerdict.REMOTE_OUTAGE


def test_an_unparsable_address_is_skipped_not_trusted(caplog):
    with caplog.at_level(logging.WARNING):
        diagnosis = classify(
            connect=all_reachable,
            resolve=lambda _h: ("not-an-ip",),
            identity_ok=lambda: False,
        )

    assert diagnosis.verdict is NetworkVerdict.REMOTE_OUTAGE
    assert any("unparsable address" in record.message for record in caplog.records)


def test_a_mixed_answer_containing_a_private_address_is_tampering():
    diagnosis = classify(
        connect=all_reachable,
        resolve=lambda _h: ("104.16.1.1", "127.0.0.1"),
        identity_ok=lambda: False,
    )

    assert diagnosis.verdict is NetworkVerdict.LOCAL_TAMPERED


def test_the_identity_probe_is_optional():
    """Callers that cannot cheaply run it still get a usable verdict."""
    diagnosis = classify(connect=all_reachable, resolve=lambda _h: PUBLIC)

    assert diagnosis.verdict is NetworkVerdict.REMOTE_OUTAGE


def test_online_is_never_our_fault():
    assert not NetworkVerdict.ONLINE.is_our_fault
    assert not NetworkVerdict.REMOTE_OUTAGE.is_our_fault


def test_tcp_reachable_reports_failure_rather_than_raising(monkeypatch):
    def refuse(*_args, **_kwargs):
        message = "refused"
        raise OSError(message)

    monkeypatch.setattr("leetcode_guard._netcheck.socket.create_connection", refuse)

    assert not tcp_reachable("192.0.2.1", 443, timeout=0.01)


def test_tcp_reachable_reports_success(monkeypatch):
    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(
        "leetcode_guard._netcheck.socket.create_connection",
        lambda *a, **k: FakeSocket(),
    )

    assert tcp_reachable("192.0.2.1", 443)


def test_resolve_host_returns_empty_on_failure(monkeypatch, caplog):
    def fail(*_args, **_kwargs):
        message = "no such host"
        raise OSError(message)

    monkeypatch.setattr("leetcode_guard._netcheck.socket.getaddrinfo", fail)

    with caplog.at_level(logging.WARNING):
        assert resolve_host(LEETCODE_HOST) == ()

    assert any("cannot resolve" in record.message for record in caplog.records)


def test_resolve_host_deduplicates_and_sorts(monkeypatch):
    monkeypatch.setattr(
        "leetcode_guard._netcheck.socket.getaddrinfo",
        lambda *a, **k: [
            (0, 0, 0, "", ("2.2.2.2", 0)),
            (0, 0, 0, "", ("1.1.1.1", 0)),
            (0, 0, 0, "", ("1.1.1.1", 0)),
        ],
    )

    assert resolve_host(LEETCODE_HOST) == ("1.1.1.1", "2.2.2.2")


def test_the_default_connect_probe_is_used_when_none_is_injected(monkeypatch):
    monkeypatch.setattr("leetcode_guard._netcheck.tcp_reachable", lambda *a, **k: False)

    assert classify(resolve=lambda _h: PUBLIC).verdict is NetworkVerdict.LOCAL_OFFLINE


def test_the_default_resolver_is_used_when_none_is_injected(monkeypatch):
    monkeypatch.setattr("leetcode_guard._netcheck.resolve_host", lambda _h: ())

    diagnosis = classify(connect=all_reachable)

    assert diagnosis.verdict is NetworkVerdict.LOCAL_TAMPERED
