"""Tests for the lock window's behaviour.

Tk is a MagicMock throughout (see ``conftest``), and gatelock's per-output
surface machinery is patched out (see ``_gatelock_fixtures``), so these run
without a display and can never grab input.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._ledger_io import load_ledger
from leetcode_guard.tests._guard_factories import (
    UNVERIFIABLE,
    create_guard,
    guard_with_fresh_solves,
    probe_of,
)
from leetcode_guard.tests._ledger_fixtures import MONDAY

if TYPE_CHECKING:
    from pathlib import Path


def test_demo_arms_with_a_local_grab_and_leaves_vt_alone(tmp_path: Path):
    """A new locker that hard-grabs on its first run is how an afternoon is
    lost, so demo is the default and it is genuinely weaker."""
    guard, _ = create_guard(tmp_path, demo_mode=True)

    assert guard.run_state.config.resolved_grab() == "local"
    assert guard.run_state.config.resolved_disable_vt() is False
    assert guard.run_state.config.resolved_overrideredirect() is True


def test_production_arms_with_a_global_grab_and_disables_vt(tmp_path: Path):
    """Production mode grabs input globally and disables VT switching."""
    guard, _ = create_guard(tmp_path, demo_mode=False)

    assert guard.run_state.config.resolved_grab() == "global"
    assert guard.run_state.config.resolved_disable_vt() is True


def test_the_arbiter_rank_sits_between_diet_guard_and_screen_locker(tmp_path: Path):
    """150, as a literal. Adding a constant to gatelock would bump its version
    and force a re-pin across three live consumers."""
    guard, _ = create_guard(tmp_path)

    assert guard.run_state.config.rank == 150


def test_overrideredirect_stays_on_even_in_demo(tmp_path: Path):
    """Per-output placement is impossible without it, so a demo that dropped it
    would not be testing the real window at all."""
    guard, _ = create_guard(tmp_path, demo_mode=True)

    assert guard.run_state.config.resolved_overrideredirect() is True


def test_colours_are_gatelocks_defaults_not_overrides(tmp_path: Path):
    """LockConfig's own defaults *are* the unified design system."""
    guard, _ = create_guard(tmp_path)

    assert guard.run_state.config.palette.bg == "#211D1B"
    assert guard.run_state.config.palette.accent == "#B8862E"
    assert guard.run_state.config.palette.on_fill == "#211D1B"


def test_a_first_run_seeds_without_writing_a_charge(tmp_path: Path, hmac_key: Path):
    """The recent feed is banked as zero-value markers and nothing else.

    Seeding used to settle its own day, which meant ``rm ledger.json`` produced
    an unlocked day -- the deferral was expressible as exactly the state the
    gate unlocks on. Skipping the *run* is what defers now; the ledger records
    no opinion about today."""
    guard, _ = create_guard(
        tmp_path, probe=probe_of("old-1", "old-2"), key_file=hmac_key
    )

    ledger = load_ledger(tmp_path / "ledger.json", key_file=hmac_key)

    assert ledger.has("ac:old-1")
    assert ledger.entries["ac:old-1"].kind == "seen"
    assert not ledger.has(f"charge:{MONDAY.isoformat()}")
    assert guard.decision().balance.available == 0


def test_the_day_after_seeding_gates_normally(tmp_path: Path, hmac_key: Path):
    """Once seeded, a day with no fresh solve stays locked."""
    guard, _ = create_guard(
        tmp_path, probe=probe_of("old-1", "old-2"), key_file=hmac_key, seeded=True
    )

    assert guard.decision().locked


def test_fresh_solves_unlock(tmp_path: Path, hmac_key: Path):
    """The done-condition, end to end: seeded, locked, then new accepted
    submissions release it.

    Two rather than one, because the seeding run settled its own day on credit
    -- that deferral is a loan, so the first solve back pays off Friday and the
    second buys today.
    """
    guard = guard_with_fresh_solves(tmp_path, hmac_key)
    assert guard.decision().locked

    guard.on_poll_result(guard.check())

    ledger = load_ledger(tmp_path / "ledger.json", key_file=hmac_key)
    assert ledger.entries["ac:brand-new"].kind == "credit"
    assert ledger.has(f"charge:{MONDAY.isoformat()}")
    assert not guard.decision().locked


def test_an_unverifiable_poll_never_unlocks_and_never_mints(
    tmp_path: Path, hmac_key: Path
):
    """ "Cannot check" must not resemble "nothing new" *or* "solved"."""
    guard, _ = create_guard(
        tmp_path,
        probe=probe_of("old-1"),
        poll_probe=UNVERIFIABLE,
        key_file=hmac_key,
        seeded=True,
    )

    guard.on_poll_result(guard.check())

    assert guard.decision().locked
    assert guard.poller.state.consecutive_unverifiable == 1


def test_consecutive_failures_accumulate_then_reset(tmp_path: Path, hmac_key: Path):
    """Unverifiable polls count up, and one good poll resets the count."""
    guard, _ = create_guard(
        tmp_path, probe=probe_of(), poll_probe=UNVERIFIABLE, key_file=hmac_key
    )

    guard.on_poll_result(UNVERIFIABLE)
    guard.on_poll_result(UNVERIFIABLE)
    assert guard.poller.state.consecutive_unverifiable == 2

    guard.on_poll_result(probe_of("fresh"))
    assert guard.poller.state.consecutive_unverifiable == 0


class _FakeSurface:
    """Minimal stand-in for gatelock's SurfaceInfo."""

    def __init__(self, output_name: str) -> None:
        self.output_name = output_name
