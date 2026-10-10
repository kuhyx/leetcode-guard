"""Tests for the browser-nudge burst and its limits.

The doorbell is unauthenticated, so the properties here are the ones that keep
a forged ring harmless: it only ever triggers checks, bursts are rate-limited,
and a failed extra check never counts as blind time.
"""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from leetcode_guard import _lock_nudge
from leetcode_guard._lock_nudge import (
    NUDGE_BURST_RETRY_MS,
    NUDGE_COOLDOWN_SECONDS,
    NUDGE_VERIFY_GRACE_MS,
)
from leetcode_guard.tests._guard_factories import (
    UNVERIFIABLE,
    create_guard,
    probe_of,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _armed(tmp_path: Path) -> MagicMock:
    guard, _calls = create_guard(tmp_path, seeded=True)
    guard._poller = MagicMock()
    guard.root.after.reset_mock()
    return guard


def test_a_ring_checks_now_and_schedules_the_retries(tmp_path: Path) -> None:
    guard = _armed(tmp_path)

    guard._bell.set()
    guard._watch_bell()

    guard._poller.check_now.assert_called_once_with()
    delays = [c.args[0] for c in guard.root.after.call_args_list]
    assert delays[: len(NUDGE_BURST_RETRY_MS)] == list(NUDGE_BURST_RETRY_MS)
    assert not guard._bell.is_set()


def test_a_second_ring_inside_the_cooldown_is_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    guard = _armed(tmp_path)
    clock = iter([1000.0, 1001.0, 1000.0 + NUDGE_COOLDOWN_SECONDS + 1])
    monkeypatch.setattr(_lock_nudge.time, "monotonic", lambda: next(clock))

    for _ in range(3):
        guard._bell.set()
        guard._watch_bell()

    assert guard._poller.check_now.call_count == 2


def test_a_quiet_bell_only_reschedules_the_watch(tmp_path: Path) -> None:
    guard = _armed(tmp_path)

    guard._watch_bell()

    guard._poller.check_now.assert_not_called()
    assert guard.root.after.call_count == 1


def test_a_closed_lock_stops_watching(tmp_path: Path) -> None:
    guard = _armed(tmp_path)
    guard._closed = True

    guard._watch_bell()

    guard.root.after.assert_not_called()


def test_a_credit_cancels_the_rest_of_the_burst(tmp_path: Path) -> None:
    guard, _calls = create_guard(tmp_path, seeded=True)
    guard._burst_jobs = ["retry-1", "retry-2"]

    guard._on_poll_result(probe_of("fresh"))

    cancelled = [c.args[0] for c in guard.root.after_cancel.call_args_list]
    assert cancelled == ["retry-1", "retry-2"]
    assert guard._burst_jobs == []


def test_a_failed_poked_check_is_not_blind_time(tmp_path: Path) -> None:
    guard, _calls = create_guard(tmp_path, seeded=True)
    guard._poller.last_was_poke = True

    guard._on_poll_result(UNVERIFIABLE)

    assert guard._poller.state.consecutive_unverifiable == 0


def test_a_failed_regular_check_still_is(tmp_path: Path) -> None:
    guard, _calls = create_guard(tmp_path, seeded=True)
    guard._poller.last_was_poke = False

    guard._on_poll_result(UNVERIFIABLE)

    assert guard._poller.state.consecutive_unverifiable == 1


def test_a_port_opens_a_real_doorbell_and_close_shuts_it(tmp_path: Path) -> None:
    guard, _calls = create_guard(tmp_path, seeded=True)

    guard._start_nudges(0)
    server = guard._nudge_server
    assert server is not None
    assert server.port is not None

    guard._stop_nudges()
    assert server.port is None


def test_a_ring_shows_the_verifying_note_and_books_its_end(tmp_path: Path) -> None:
    guard = _armed(tmp_path)
    guard._refresh_strip = MagicMock()

    guard._bell.set()
    guard._watch_bell()

    assert guard.nudge_verifying
    guard._refresh_strip.assert_called_once_with()
    delays = [c.args[0] for c in guard.root.after.call_args_list]
    assert NUDGE_BURST_RETRY_MS[-1] + NUDGE_VERIFY_GRACE_MS in delays


def test_a_burst_that_runs_out_drops_the_note(tmp_path: Path) -> None:
    """A forged ring must not leave a claim on screen."""
    guard = _armed(tmp_path)
    guard._refresh_strip = MagicMock()
    guard.nudge_verifying = True
    guard._burst_jobs = ["retry-1"]

    guard._burst_ran_out()

    assert not guard.nudge_verifying
    assert guard._burst_jobs == []
    guard._refresh_strip.assert_called_once_with()


def test_a_credit_drops_the_note(tmp_path: Path) -> None:
    guard, _calls = create_guard(tmp_path, seeded=True)
    guard.nudge_verifying = True

    guard._on_poll_result(probe_of("fresh"))

    assert not guard.nudge_verifying


def test_a_taken_port_marks_the_doorbell_down(tmp_path: Path) -> None:
    """2026-10-10: another app held 8772 and the lock only logged it."""
    guard, _calls = create_guard(tmp_path, seeded=True)
    with socket.socket() as squatter:
        squatter.bind(("127.0.0.1", 0))
        squatter.listen()
        guard._start_nudges(squatter.getsockname()[1])

    assert guard.nudge_down
    guard._stop_nudges()
