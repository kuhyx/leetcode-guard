"""Continued from :mod:`leetcode_guard.tests.test_status_view`, split for the 250-line cap."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard import status_view
from leetcode_guard._status_full import explain_not_triggered, gather_full
from leetcode_guard._status_timer import (
    gather_timer,
)
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    add_charge,
    ledger_with_credits,
)

if TYPE_CHECKING:
    from pathlib import Path

from leetcode_guard.tests.test_status_view import (
    MONDAY_NOON,
    full_for,
)


def test_a_disabled_timer_is_reported():
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
    from leetcode_guard import _status_full, _status_timer

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
    ledger = ledger_with_credits(3, day=MONDAY, key_file=hmac_key)

    reasons = explain_not_triggered(full_for(data_dir, hmac_key, ledger))

    assert any("banked" in line for line in reasons)


def test_an_already_settled_day_is_explained_as_such(data_dir: Path, hmac_key: Path):
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    add_charge(ledger, MONDAY, key_file=hmac_key)

    reasons = explain_not_triggered(full_for(data_dir, hmac_key, ledger))

    assert any("already settled" in line for line in reasons)


def test_a_locked_gate_says_it_would_lock(data_dir: Path, hmac_key: Path):
    reasons = explain_not_triggered(full_for(data_dir, hmac_key))

    assert any("WOULD lock" in line for line in reasons)


def test_refused_credits_are_explained(data_dir: Path, hmac_key: Path):
    from leetcode_guard._ledger_io import append
    from leetcode_guard.tests._ledger_fixtures import forged_credit

    ledger = ledger_with_credits(2, day=MONDAY, key_file=hmac_key)
    append(ledger, [forged_credit()])

    reasons = explain_not_triggered(full_for(data_dir, hmac_key, ledger))

    assert any("REFUSED" in line for line in reasons)


def test_an_unreadable_key_is_explained(data_dir: Path, missing_key: Path):
    path = data_dir / "ledger.json"
    full = gather_full(now=MONDAY_NOON, ledger_path=path, key_file=missing_key)

    assert any(
        "integrity checking is OFF" in line for line in explain_not_triggered(full)
    )


def test_state_word_tracks_the_verdict(data_dir: Path, hmac_key: Path):
    locked = full_for(data_dir, hmac_key)
    banked = full_for(
        data_dir, hmac_key, ledger_with_credits(3, day=MONDAY, key_file=hmac_key)
    )

    assert status_view.state_word(locked) == status_view.STATE_LOCK
    assert status_view.state_word(banked) == status_view.STATE_OK


def test_summary_line_names_the_shortfall(data_dir: Path, hmac_key: Path):
    line = status_view.summary_line(full_for(data_dir, hmac_key))

    assert line.startswith("LOCKED")
    assert "solve 1 problem" in line


def test_summary_line_pluralises(data_dir: Path, hmac_key: Path, monkeypatch):

    full = full_for(data_dir, hmac_key)
    saturday = type(full.gate)(
        **{**vars(full.gate), "needed": 2, "weekday": "Saturday", "cost": 2}
    )
    combined = type(full)(**{**vars(full), "gate": saturday})

    assert "solve 2 problems" in status_view.summary_line(combined)


def test_summary_line_when_unlocked(data_dir: Path, hmac_key: Path):
    full = full_for(
        data_dir, hmac_key, ledger_with_credits(3, day=MONDAY, key_file=hmac_key)
    )

    assert status_view.summary_line(full).startswith("Unlocked")


def test_the_flags_print_one_line_each(capsys, data_dir: Path):
    assert status_view.main(["--state"]) == 0
    assert capsys.readouterr().out.strip() in {"ok", "warn", "lock"}

    assert status_view.main(["--summary"]) == 0
    assert capsys.readouterr().out.strip()
