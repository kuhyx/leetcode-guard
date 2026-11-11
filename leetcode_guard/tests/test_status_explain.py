"""Tests for ``explain_not_triggered``, the timer probe and the default gather.

What the snapshot's ``status.explanation`` carries. Salvaged from the deleted
tkinter window's tests: the rendering went, the reasons it rendered stayed.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _status_full, _status_timer
from leetcode_guard._ledger_io import append
from leetcode_guard._status_full import explain_not_triggered, gather_full
from leetcode_guard._status_timer import _run_systemctl, gather_timer
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    add_charge,
    forged_credit,
    ledger_with_credits,
)
from leetcode_guard.tests.test_status_gather import MONDAY_NOON, full_for

if TYPE_CHECKING:
    from pathlib import Path


def test_a_disabled_timer_is_reported():
    """A timer systemd says is disabled reports not enabled and never scheduled."""
    timer = gather_timer(
        run=lambda args: "disabled\n" if args[0] == "is-enabled" else "X=\n"
    )

    assert not timer.enabled
    assert timer.next_fire == "not scheduled"


def test_a_disabled_timer_is_the_first_thing_explained(
    data_dir: Path, hmac_key: Path, monkeypatch
):
    """ "Unlocked" with the timer off means the gate never even ran, which looks
    identical from outside to having banked credit."""
    monkeypatch.setattr(
        _status_timer,
        "gather_timer",
        lambda **_k: _status_timer.TimerStatus(
            enabled=False, next_fire="never", detail="disabled"
        ),
    )
    monkeypatch.setattr(_status_full, "gather_timer", _status_timer.gather_timer)

    reasons = explain_not_triggered(full_for(data_dir, hmac_key))

    assert "NOT enabled" in reasons[0]


def test_banked_credit_is_explained_as_such(data_dir: Path, hmac_key: Path):
    """Unused credits on the day explain the unlock as banked credit."""
    ledger = ledger_with_credits(3, day=MONDAY, key_file=hmac_key)

    reasons = explain_not_triggered(full_for(data_dir, hmac_key, ledger))

    assert any("banked" in line for line in reasons)


def test_an_already_settled_day_is_explained_as_such(data_dir: Path, hmac_key: Path):
    """A day that already has a charge is explained as already settled."""
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    add_charge(ledger, MONDAY, key_file=hmac_key)

    reasons = explain_not_triggered(full_for(data_dir, hmac_key, ledger))

    assert any("already settled" in line for line in reasons)


def test_a_locked_gate_says_it_would_lock(data_dir: Path, hmac_key: Path):
    """With no credit, the explanation states the gate would lock."""
    reasons = explain_not_triggered(full_for(data_dir, hmac_key))

    assert any("WOULD lock" in line for line in reasons)


def test_refused_credits_are_explained(data_dir: Path, hmac_key: Path):
    """Credits that fail their HMAC are called out as refused, not silently dropped."""
    ledger = ledger_with_credits(2, day=MONDAY, key_file=hmac_key)
    append(ledger, [forged_credit()])

    reasons = explain_not_triggered(full_for(data_dir, hmac_key, ledger))

    assert any("REFUSED" in line for line in reasons)
    assert any("failed their signature" in line for line in reasons)


def test_an_unreadable_key_is_explained(data_dir: Path, missing_key: Path):
    """A missing signing key is explained as integrity checking being off."""
    path = data_dir / "ledger.json"
    full = gather_full(now=MONDAY_NOON, ledger_path=path, key_file=missing_key)

    assert any(
        "integrity checking is OFF" in line for line in explain_not_triggered(full)
    )


def test_unreadable_rows_are_reported(data_dir: Path, hmac_key: Path):
    """Junk ledger rows are reported as rows that could not be read."""
    path = data_dir / "ledger.json"
    path.write_text('{"version": 1, "entries": [{"junk": 1}]}', encoding="utf-8")

    reasons = explain_not_triggered(
        gather_full(now=MONDAY_NOON, ledger_path=path, key_file=hmac_key)
    )

    assert any("could not be read" in line for line in reasons)


def test_an_untrusted_clock_is_reported(data_dir: Path, hmac_key: Path):
    """An entry dated after now is reported as the clock having moved backwards."""
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    add_charge(ledger, MONDAY + timedelta(days=5), key_file=hmac_key)

    reasons = explain_not_triggered(full_for(data_dir, hmac_key, ledger))

    assert any("moved backwards" in line for line in reasons)


def _not_started(full, *, reason: str, in_force: bool):
    verdict = replace(
        full.gate.verdict, state="not-started", locked=False, reason=reason
    )
    return replace(
        full,
        gate=replace(full.gate, verdict=verdict),
        setup=replace(full.setup, in_force=in_force),
    )


def test_the_not_started_reason_shows_once_the_gate_is_in_force(
    data_dir: Path, hmac_key: Path
):
    """Belt and braces: the reason is suppressed only while the dedicated
    not-in-force line is already saying it."""
    full = _not_started(full_for(data_dir, hmac_key), reason="custom", in_force=True)

    assert "custom" in explain_not_triggered(full)


def test_the_not_in_force_line_suppresses_the_duplicate_reason(
    data_dir: Path, hmac_key: Path
):
    """Both would otherwise say "does not start until", reading as two causes."""
    full = _not_started(full_for(data_dir, hmac_key), reason="dupe", in_force=False)

    reasons = explain_not_triggered(full)

    assert "dupe" not in reasons
    assert any("not in force" in line for line in reasons)


def test_an_enabled_timer_adds_no_line(data_dir: Path, hmac_key: Path):
    """The counterpart to the disabled-timer test: CI has no user timer, so
    without it the enabled branch was covered only by ambient machine state."""
    full = full_for(data_dir, hmac_key)
    on = type(full.timer)(enabled=True, next_fire="Tue 09:00", detail="enabled")
    combined = type(full)(**{**vars(full), "timer": on})

    reasons = explain_not_triggered(combined)

    assert not any("timer is NOT enabled" in line for line in reasons)


def test_run_systemctl_reports_failure_as_none(monkeypatch, caplog):
    """A missing systemctl yields None plus a warning instead of raising."""

    def explode(*_args, **_kwargs):
        message = "no systemctl"
        raise OSError(message)

    monkeypatch.setattr(_status_timer.subprocess, "run", explode)

    with caplog.at_level(logging.WARNING):
        assert _run_systemctl(["is-enabled", "x.timer"]) is None

    assert any("could not query systemd" in r.message for r in caplog.records)


def test_run_systemctl_returns_stdout(monkeypatch):
    """A successful systemctl call hands back its raw stdout."""

    monkeypatch.setattr(
        _status_timer.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout="enabled\n"),
    )

    assert _run_systemctl(["is-enabled", "x.timer"]) == "enabled\n"


@pytest.mark.usefixtures("data_dir")
def test_the_default_gather_reads_the_isolated_paths():
    """With no arguments, gather_full uses the isolated default ledger path."""
    full = gather_full()

    assert full.setup.ledger_path.endswith("ledger.json")
    assert not full.setup.sync_configured
    assert not full.setup.cookies_configured
