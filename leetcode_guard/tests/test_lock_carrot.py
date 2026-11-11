"""An armed lock takes itself down when a signed morning carrot lands later.

Incident 2026-11-07: the gate armed at 07:49 because wake-alarm's signed
``morning_session.json`` had not landed yet (it did at 07:50) and an armed lock
never looked again. These tests pin the late re-check: it reuses the clean
stand-down a verified solve uses, writes no ledger state, and only ever runs
between 05:00 and 11:00 local.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import json
import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from gatelock import log_integrity
from gatelock.log_integrity import compute_entry_hmac
import pytest

from leetcode_guard import _lock_carrot, _morning_session
from leetcode_guard._gatelock_internals import arming, set_arming
from leetcode_guard._lock_carrot import CARROT_POLL_MS
from leetcode_guard._lock_poll import _UNLOCK_LINGER_MS
from leetcode_guard.tests._guard_factories import create_guard, probe_of

if TYPE_CHECKING:
    from pathlib import Path

URL = "https://leetcode.com/problems/two-sum/"


@pytest.fixture(autouse=True)
def _signing_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    key = tmp_path / "carrot.key"
    key.write_bytes(b"1" * 32)
    monkeypatch.setattr(log_integrity, "DEFAULT_HMAC_KEY_FILE", key)


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, 7, hour, minute).astimezone()


def _write_carrot(day: str = "2026-11-07", exempt_until: str = "23:00") -> None:
    entry: dict[str, object] = {
        "date": day,
        "outcome": "in_progress",
        "exempt_until": datetime.fromisoformat(f"{day}T{exempt_until}")
        .astimezone()
        .isoformat(),
    }
    entry["hmac"] = compute_entry_hmac(entry)
    _morning_session.MORNING_SESSION_FILE.write_text(json.dumps(entry))


def armed(tmp_path: Path, hmac_key: Path, *, at: datetime):
    """A production-config guard on an ordinary gating day, grab mocks swapped in."""
    guard, _ = create_guard(
        tmp_path,
        probe=probe_of("old-1"),
        key_file=hmac_key,
        seeded=True,
        demo_mode=False,
        now=at,
    )
    set_arming(
        guard.lock,
        replace(arming(guard.lock), recovery=MagicMock(), detector=MagicMock()),
    )
    return guard


def _scheduled(guard, func) -> list[tuple]:
    """The ``root.after`` calls that registered ``func``."""
    return [c.args for c in guard.root.after.call_args_list if c.args[1] == func]


def test_arming_schedules_the_first_check(tmp_path: Path, hmac_key: Path) -> None:
    """Arming a real lock queues the first carrot check one poll interval out."""
    guard = armed(tmp_path, hmac_key, at=_at(7, 49))
    assert _scheduled(guard, guard.carrot_tick) == [(CARROT_POLL_MS, guard.carrot_tick)]
    assert CARROT_POLL_MS == 15_000


@pytest.mark.usefixtures("hmac_key")
def test_a_demo_lock_never_reads_the_morning_session(tmp_path: Path) -> None:
    """A demo lock schedules no carrot check at all."""
    guard, _ = create_guard(tmp_path, demo_mode=True, now=_at(7, 49))
    assert _scheduled(guard, guard.carrot_tick) == []


def test_a_signed_carrot_stands_the_lock_down(
    tmp_path: Path, hmac_key: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A signed carrot unlocks with a warning, no ledger write and no reschedule."""
    guard = armed(tmp_path, hmac_key, at=_at(7, 50))
    ledger_before = (tmp_path / "ledger.json").read_bytes()
    _write_carrot()

    with caplog.at_level(logging.WARNING):
        guard.carrot_tick()

    assert (_UNLOCK_LINGER_MS, guard.close) in [
        c.args for c in guard.root.after.call_args_list
    ]
    warned = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("morning session" in r.getMessage() for r in warned)
    # A deferral is not a solve: nothing is credited or charged.
    assert (tmp_path / "ledger.json").read_bytes() == ledger_before
    # And the check cancels the pending reschedule instead of repeating.
    guard.root.after_cancel.assert_called()
    assert guard.carrot_job is None


@pytest.mark.usefixtures("no_spawn")
def test_the_stand_down_ends_study_mode_and_stops_recovery(
    tmp_path: Path, hmac_key: Path
) -> None:
    """Releasing the X grab while RecoveryLoop runs leaves a focused window that
    swallows every key. The solve path ends study (resume), then gatelock's
    ``close`` stops recovery before the grab goes; the carrot path must too."""
    guard = armed(tmp_path, hmac_key, at=_at(7, 50))
    recovery = MagicMock()
    set_arming(guard.lock, replace(arming(guard.lock), recovery=recovery))
    guard.open_problem(URL)
    assert guard.session().active
    _write_carrot()

    guard.carrot_tick()
    assert not guard.session().active
    assert guard.strip is None
    guard.close()

    assert recovery.stop.called
    assert guard.run_state.closed


def test_no_carrot_keeps_the_lock_and_reschedules(
    tmp_path: Path, hmac_key: Path
) -> None:
    """With no carrot on disk the lock stays and the check is queued again."""
    guard = armed(tmp_path, hmac_key, at=_at(7, 50))

    guard.carrot_tick()

    assert len(_scheduled(guard, guard.carrot_tick)) == 2
    assert (_UNLOCK_LINGER_MS, guard.close) not in [
        c.args for c in guard.root.after.call_args_list
    ]
    assert not guard.run_state.closed


def test_yesterdays_or_expired_carrot_keeps_the_lock(
    tmp_path: Path, hmac_key: Path
) -> None:
    """A carrot from another day or past its exemption never unlocks."""
    guard = armed(tmp_path, hmac_key, at=_at(7, 50))
    _write_carrot(day="2026-11-06")
    guard.carrot_tick()
    _write_carrot(exempt_until="07:00")
    guard.carrot_tick()
    assert (_UNLOCK_LINGER_MS, guard.close) not in [
        c.args for c in guard.root.after.call_args_list
    ]
    assert len(_scheduled(guard, guard.carrot_tick)) == 3


@pytest.mark.parametrize("when", [_at(4, 59), _at(11, 0), _at(23, 30)])
def test_outside_the_morning_window_the_file_is_not_even_read(
    tmp_path: Path, hmac_key: Path, when: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Outside 05:00-11:00 the check reschedules without reading the carrot."""
    guard = armed(tmp_path, hmac_key, at=when)
    _write_carrot()
    reads = MagicMock(return_value="would defer")
    monkeypatch.setattr(_lock_carrot, "defer_for_morning_session", reads)

    guard.carrot_tick()

    reads.assert_not_called()
    assert len(_scheduled(guard, guard.carrot_tick)) == 2
    assert not guard.run_state.closed


def test_the_poll_never_waits(
    tmp_path: Path, hmac_key: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The carrot check reads the session without blocking the Tk loop."""
    guard = armed(tmp_path, hmac_key, at=_at(7, 50))
    reads = MagicMock(return_value=None)
    monkeypatch.setattr(_lock_carrot, "defer_for_morning_session", reads)

    guard.carrot_tick()

    assert reads.call_args.kwargs == {"wait": False}


def test_a_reader_crash_is_logged_and_the_lock_keeps_watching(
    tmp_path: Path,
    hmac_key: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing carrot reader is logged and the lock keeps polling."""
    guard = armed(tmp_path, hmac_key, at=_at(7, 50))
    monkeypatch.setattr(
        _lock_carrot, "defer_for_morning_session", MagicMock(side_effect=OSError("io"))
    )

    with caplog.at_level(logging.WARNING):
        guard.carrot_tick()

    assert any("could not read" in r.getMessage() for r in caplog.records)
    assert len(_scheduled(guard, guard.carrot_tick)) == 2
    assert not guard.run_state.closed


def test_a_closed_lock_stops_the_watch(tmp_path: Path, hmac_key: Path) -> None:
    """A tick after close does not schedule another check."""
    guard = armed(tmp_path, hmac_key, at=_at(7, 50))
    guard.close()

    guard.carrot_tick()

    assert len(_scheduled(guard, guard.carrot_tick)) == 1


def test_closing_cancels_the_pending_check(tmp_path: Path, hmac_key: Path) -> None:
    """Closing the lock cancels the queued carrot check."""
    guard = armed(tmp_path, hmac_key, at=_at(7, 50))
    job = guard.carrot_job
    assert job is not None

    guard.close()

    guard.root.after_cancel.assert_any_call(job)
    assert guard.carrot_job is None
