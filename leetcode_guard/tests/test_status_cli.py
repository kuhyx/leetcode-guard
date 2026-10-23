"""Tests for the tray's one-line CLIs, ``--state`` and ``--summary``.

They outlived the tkinter window they used to share a module with: the tray
still colours its icon and fills its tooltip from them, and its click falls
back to ``--summary`` when the status app's launcher is missing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard import status_cli
from leetcode_guard.tests._ledger_fixtures import MONDAY, ledger_with_credits
from leetcode_guard.tests.test_status_gather import full_for

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_state_word_tracks_the_verdict(data_dir: Path, hmac_key: Path):
    locked = full_for(data_dir, hmac_key)
    banked = full_for(
        data_dir, hmac_key, ledger_with_credits(3, day=MONDAY, key_file=hmac_key)
    )

    assert status_cli.state_word(locked) == status_cli.STATE_LOCK
    assert status_cli.state_word(banked) == status_cli.STATE_OK


def test_the_state_word_warns_with_nothing_banked(data_dir: Path, hmac_key: Path):
    full = full_for(data_dir, hmac_key)
    gate = type(full.gate)(**{**vars(full.gate), "locked": False, "available": 0})
    combined = type(full)(**{**vars(full), "gate": gate})

    assert status_cli.state_word(combined) == status_cli.STATE_WARN


def test_summary_line_names_the_shortfall(data_dir: Path, hmac_key: Path):
    line = status_cli.summary_line(full_for(data_dir, hmac_key))

    assert line.startswith("LOCKED")
    assert "solve 1 problem" in line


def test_summary_line_pluralises(data_dir: Path, hmac_key: Path):
    full = full_for(data_dir, hmac_key)
    saturday = type(full.gate)(
        **{**vars(full.gate), "needed": 2, "weekday": "Saturday", "cost": 2}
    )
    combined = type(full)(**{**vars(full), "gate": saturday})

    assert "solve 2 problems" in status_cli.summary_line(combined)


def test_summary_line_when_unlocked(data_dir: Path, hmac_key: Path):
    full = full_for(
        data_dir, hmac_key, ledger_with_credits(3, day=MONDAY, key_file=hmac_key)
    )

    assert status_cli.summary_line(full).startswith("Unlocked")


def test_summary_line_names_the_debt(data_dir: Path, hmac_key: Path):
    full = full_for(data_dir, hmac_key)
    owing = type(full.gate)(**{**vars(full.gate), "debt_outstanding": 9})
    combined = type(full)(**{**vars(full), "gate": owing})

    assert "debt 9" in status_cli.summary_line(combined)


def test_the_summary_line_reports_a_gate_not_yet_in_force(
    data_dir: Path, hmac_key: Path
):
    full = full_for(data_dir, hmac_key)
    gate = type(full.gate)(
        **{
            **vars(full.gate),
            "state": "not-started",
            "locked": False,
            "reason": "not yet",
        }
    )
    combined = type(full)(**{**vars(full), "gate": gate})

    assert status_cli.summary_line(combined) == "leetcode-guard: not yet"


def test_the_flags_print_one_line_each(
    capsys: pytest.CaptureFixture[str], data_dir: Path
):
    assert status_cli.main(["--state"]) == 0
    assert capsys.readouterr().out.strip() in {"ok", "warn", "lock"}

    assert status_cli.main(["--summary"]) == 0
    assert capsys.readouterr().out.strip()


def test_no_flag_prints_the_summary_and_opens_no_window(
    capsys: pytest.CaptureFixture[str], data_dir: Path
):
    """The window is the status app now; a bare call must not hang on Tk."""
    assert status_cli.main([]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    assert out[0] not in {"ok", "warn", "lock"}


def test_main_reads_sys_argv_by_default(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    data_dir: Path,
):
    monkeypatch.setattr(status_cli.sys, "argv", ["leetcode-guard-status", "--state"])

    assert status_cli.main() == 0
    assert capsys.readouterr().out.strip() in {"ok", "warn", "lock"}
