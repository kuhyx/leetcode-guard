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
    """Build a seeded guard with a mock poller and a clean after() log."""
    guard, _calls = create_guard(tmp_path, seeded=True)
    guard.poller = MagicMock()
    MagicMock.reset_mock(guard.root.after)
    return guard


def test_a_ring_checks_now_and_schedules_the_retries(tmp_path: Path) -> None:
    """A ring triggers one check now and books every burst retry."""
    guard = _armed(tmp_path)

    guard.bell.set()
    guard.watch_bell()

    guard.poller.check_now.assert_called_once_with()
    delays = [c.args[0] for c in guard.root.after.call_args_list]
    assert delays[: len(NUDGE_BURST_RETRY_MS)] == list(NUDGE_BURST_RETRY_MS)
    assert not guard.bell.is_set()


def test_a_second_ring_inside_the_cooldown_is_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rings inside the cooldown window trigger no extra check."""
    guard = _armed(tmp_path)
    clock = iter([1000.0, 1001.0, 1000.0 + NUDGE_COOLDOWN_SECONDS + 1])
    monkeypatch.setattr(_lock_nudge.time, "monotonic", lambda: next(clock))

    for _ in range(3):
        guard.bell.set()
        guard.watch_bell()

    assert guard.poller.check_now.call_count == 2


def test_a_quiet_bell_only_reschedules_the_watch(tmp_path: Path) -> None:
    """An unrung bell checks nothing and only re-arms the watch."""
    guard = _armed(tmp_path)

    guard.watch_bell()

    guard.poller.check_now.assert_not_called()
    assert guard.root.after.call_count == 1


def test_a_closed_lock_stops_watching(tmp_path: Path) -> None:
    """A closed lock schedules no further bell watch."""
    guard = _armed(tmp_path)
    guard.run_state.closed = True

    guard.watch_bell()

    guard.root.after.assert_not_called()


def test_a_credit_cancels_the_rest_of_the_burst(tmp_path: Path) -> None:
    """A credited solve cancels every pending burst retry."""
    guard, _calls = create_guard(tmp_path, seeded=True)
    guard.burst_jobs = ["retry-1", "retry-2"]

    guard.on_poll_result(probe_of("fresh"))

    cancelled = [c.args[0] for c in guard.root.after_cancel.call_args_list]
    assert cancelled == ["retry-1", "retry-2"]
    assert guard.burst_jobs == []


def test_a_failed_poked_check_is_not_blind_time(tmp_path: Path) -> None:
    """An unverifiable check triggered by a ring adds no blind time."""
    guard, _calls = create_guard(tmp_path, seeded=True)
    guard.poller.last_was_poke = True

    guard.on_poll_result(UNVERIFIABLE)

    assert guard.poller.state.consecutive_unverifiable == 0


def test_a_failed_regular_check_still_is(tmp_path: Path) -> None:
    """An unverifiable scheduled check still counts as blind time."""
    guard, _calls = create_guard(tmp_path, seeded=True)
    guard.poller.last_was_poke = False

    guard.on_poll_result(UNVERIFIABLE)

    assert guard.poller.state.consecutive_unverifiable == 1


def test_a_port_opens_a_real_doorbell_and_close_shuts_it(tmp_path: Path) -> None:
    """A port starts a listening doorbell that stopping closes."""
    guard, _calls = create_guard(tmp_path, seeded=True)

    guard.start_nudges(0)
    server = guard.nudge_server
    assert server is not None
    assert server.port is not None

    guard.stop_nudges()
    assert server.port is None


def test_a_ring_shows_the_verifying_note_and_books_its_end(tmp_path: Path) -> None:
    """A ring shows the verifying note and schedules its removal."""
    guard = _armed(tmp_path)
    guard.refresh_strip = MagicMock()

    guard.bell.set()
    guard.watch_bell()

    assert guard.nudge_verifying
    guard.refresh_strip.assert_called_once_with()
    delays = [c.args[0] for c in guard.root.after.call_args_list]
    assert NUDGE_BURST_RETRY_MS[-1] + NUDGE_VERIFY_GRACE_MS in delays


def test_a_burst_that_runs_out_drops_the_note(tmp_path: Path) -> None:
    """A forged ring must not leave a claim on screen."""
    guard = _armed(tmp_path)
    guard.refresh_strip = MagicMock()
    guard.nudge_verifying = True
    guard.burst_jobs = ["retry-1"]

    guard.burst_ran_out()

    assert not guard.nudge_verifying
    assert guard.burst_jobs == []
    guard.refresh_strip.assert_called_once_with()


def test_a_credit_drops_the_note(tmp_path: Path) -> None:
    """A credited solve clears the verifying note."""
    guard, _calls = create_guard(tmp_path, seeded=True)
    guard.nudge_verifying = True

    guard.on_poll_result(probe_of("fresh"))

    assert not guard.nudge_verifying


def test_a_taken_port_marks_the_doorbell_down(tmp_path: Path) -> None:
    """2026-10-10: another app held 8772 and the lock only logged it."""
    guard, _calls = create_guard(tmp_path, seeded=True)
    with socket.socket() as squatter:
        squatter.bind(("127.0.0.1", 0))
        squatter.listen()
        guard.start_nudges(squatter.getsockname()[1])

    assert guard.nudge_down
    guard.stop_nudges()
