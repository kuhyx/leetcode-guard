"""The lock's own poll mints theory credits and clears itself on a paid day.

SPEC "Guard rules for the new credit": minting runs in the one-minute
harvester AND in the lock's poll, because the harvester stands aside while a
lock is up. Without the lock's poll a day paid by teaching minutes alone would
stay locked until the window was closed some other way.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard import _phase_file
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard.tests._guard_factories import create_guard, probe_of
from leetcode_guard.tests._ledger_fixtures import MONDAY, NOW
from leetcode_guard.tests._theory_scenario import began, states, taught, world

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _theory_guard(tmp_path: Path, hmac_key: Path, *, demo_mode: bool):
    """A seeded Monday lock in THEORY(a) with 24 taught minutes on module ``a``.

    Two credits, because the seeding run settled its own Friday on credit and
    the first credit back repays it (``test_lock.test_fresh_solves_unlock``).
    """
    guard, _ = create_guard(
        tmp_path,
        demo_mode=demo_mode,
        probe=probe_of("old-1"),
        key_file=hmac_key,
        seeded=True,
    )
    states(hmac_key)
    began(hmac_key)
    taught(hmac_key, NOW, ("a", 24))
    return guard


def test_theory_minutes_pay_the_day_and_the_lock_clears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hmac_key: Path
):
    """No new solve at all: the taught minutes alone settle Monday and release."""
    world(tmp_path, monkeypatch)
    guard = _theory_guard(tmp_path, hmac_key, demo_mode=False)
    assert guard.decision().locked

    guard.on_poll_result(guard.check())

    ledger = load_ledger(tmp_path / "ledger.json", key_file=hmac_key)
    day = MONDAY.isoformat()
    assert ledger.entries[f"theory:{day}:1"].detail["source"] == "tutor-theory"
    assert ledger.has(f"theory:{day}:2")
    assert ledger.has(f"charge:{day}")
    assert not guard.decision().locked
    guard.root.after.assert_called_with(3000, guard.close)


def test_the_demo_lock_never_polls_theory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hmac_key: Path
):
    """The demo must not mint from real minutes nor rewrite the live C3 file."""
    world(tmp_path, monkeypatch)
    guard = _theory_guard(tmp_path, hmac_key, demo_mode=True)
    c3 = _phase_file.PHASE_FILE.read_bytes()

    guard.on_poll_result(guard.check())

    ledger = load_ledger(tmp_path / "ledger.json", key_file=hmac_key)
    assert not any(key.startswith("theory:") for key in ledger.entries)
    assert _phase_file.PHASE_FILE.read_bytes() == c3
