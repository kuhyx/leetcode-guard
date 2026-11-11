"""Tests for the tray's one-line CLIs, ``--state`` and ``--summary``.

They outlived the tkinter window they used to share a module with: the tray
still colours its icon and fills its tooltip from them, and its click falls
back to ``--summary`` when the status app's launcher is missing.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _glyphs as g
from leetcode_guard import status_cli
from leetcode_guard.tests._ledger_fixtures import MONDAY, ledger_with_credits
from leetcode_guard.tests.test_status_gather import full_for

if TYPE_CHECKING:
    from pathlib import Path


def test_state_word_tracks_the_verdict(data_dir: Path, hmac_key: Path):
    """The state word is lock while locked and ok with credits banked."""
    locked = full_for(data_dir, hmac_key)
    banked = full_for(
        data_dir, hmac_key, ledger_with_credits(3, day=MONDAY, key_file=hmac_key)
    )

    assert status_cli.state_word(locked) == status_cli.STATE_LOCK
    assert status_cli.state_word(banked) == status_cli.STATE_OK


def test_the_state_word_warns_with_nothing_banked(data_dir: Path, hmac_key: Path):
    """Unlocked with zero credits available reads as warn."""
    full = full_for(data_dir, hmac_key)
    gate = replace(
        full.gate,
        verdict=replace(full.gate.verdict, locked=False),
        balance=replace(full.gate.balance, available=0),
    )
    combined = replace(full, gate=gate)

    assert status_cli.state_word(combined) == status_cli.STATE_WARN


def test_summary_line_names_the_shortfall(data_dir: Path, hmac_key: Path):
    """A locked summary says LOCKED and how many solves are missing."""
    line = status_cli.summary_line(full_for(data_dir, hmac_key))

    assert line.startswith(f"{g.OWED}{g.SEP}")
    assert f"{g.CREDIT} 0" in line


def test_summary_line_draws_a_circle_per_solve(data_dir: Path, hmac_key: Path):
    """Each owed solve draws one circle on the summary line."""
    full = full_for(data_dir, hmac_key)
    saturday = replace(
        full.gate,
        verdict=replace(full.gate.verdict, needed=2),
        weekday="Saturday",
        cost=2,
    )
    combined = replace(full, gate=saturday)

    line = status_cli.summary_line(combined)
    assert line.startswith(f"{g.OWED * 2}{g.SEP}")
    assert f"{g.TODAY} 2" in line


def test_summary_line_when_unlocked(data_dir: Path, hmac_key: Path):
    """With credits banked the summary starts with Unlocked."""
    full = full_for(
        data_dir, hmac_key, ledger_with_credits(3, day=MONDAY, key_file=hmac_key)
    )

    assert status_cli.summary_line(full).startswith(f"{g.SOLVED}{g.SEP}")


def test_summary_line_names_the_debt(data_dir: Path, hmac_key: Path):
    """Outstanding debt appears in the summary as 'debt N'."""
    full = full_for(data_dir, hmac_key)
    debt = full.gate.debt
    owing = replace(full.gate, debt=replace(debt, owed=debt.repaid + 9))
    combined = replace(full, gate=owing)

    assert status_cli.summary_line(combined).endswith(f"{g.DEBT} 9")


def test_the_summary_line_reports_a_gate_not_yet_in_force(
    data_dir: Path, hmac_key: Path
):
    """A not-started gate summarises as its reason alone."""
    full = full_for(data_dir, hmac_key)
    verdict = replace(
        full.gate.verdict, state="not-started", locked=False, reason="not yet"
    )
    combined = replace(full, gate=replace(full.gate, verdict=verdict))

    assert status_cli.summary_line(combined) == g.NOT_STARTED


@pytest.mark.usefixtures("data_dir")
def test_the_flags_print_one_line_each(capsys: pytest.CaptureFixture[str]):
    """--state prints a state word and --summary a non-empty line."""
    assert status_cli.main(["--state"]) == 0
    assert capsys.readouterr().out.strip() in {"ok", "warn", "lock"}

    assert status_cli.main(["--summary"]) == 0
    assert capsys.readouterr().out.strip()


@pytest.mark.usefixtures("data_dir")
def test_no_flag_prints_the_summary_and_opens_no_window(
    capsys: pytest.CaptureFixture[str],
):
    """The window is the status app now; a bare call must not hang on Tk."""
    assert status_cli.main([]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    assert out[0] not in {"ok", "warn", "lock"}


@pytest.mark.usefixtures("data_dir")
def test_main_reads_sys_argv_by_default(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """main() with no argv falls back to sys.argv."""
    monkeypatch.setattr(status_cli.sys, "argv", ["leetcode-guard-status", "--state"])

    assert status_cli.main() == 0
    assert capsys.readouterr().out.strip() in {"ok", "warn", "lock"}
