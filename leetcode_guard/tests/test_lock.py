"""Tests for the lock window's behaviour.

Tk is a MagicMock throughout (see ``conftest``), and gatelock's per-output
surface machinery is patched out (see ``_gatelock_fixtures``), so these run
without a display and can never grab input.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._ledger_io import load_ledger
from leetcode_guard._submissions import ProbeStatus
from leetcode_guard.tests._guard_factories import (
    UNVERIFIABLE,
    create_guard,
    probe_of,
)
from leetcode_guard.tests._ledger_fixtures import MONDAY

if TYPE_CHECKING:
    from pathlib import Path


def test_demo_arms_with_a_local_grab_and_leaves_vt_alone(tmp_path: Path):
    """A new locker that hard-grabs on its first run is how an afternoon is
    lost, so demo is the default and it is genuinely weaker."""
    guard, _ = create_guard(tmp_path, demo_mode=True)

    assert guard._config.resolved_grab() == "local"
    assert guard._config.resolved_disable_vt() is False
    assert guard._config.resolved_overrideredirect() is True


def test_production_arms_with_a_global_grab_and_disables_vt(tmp_path: Path):
    guard, _ = create_guard(tmp_path, demo_mode=False)

    assert guard._config.resolved_grab() == "global"
    assert guard._config.resolved_disable_vt() is True


def test_the_arbiter_rank_sits_between_diet_guard_and_screen_locker(tmp_path: Path):
    """150, as a literal. Adding a constant to gatelock would bump its version
    and force a re-pin across three live consumers."""
    guard, _ = create_guard(tmp_path)

    assert guard._config.rank == 150


def test_overrideredirect_stays_on_even_in_demo(tmp_path: Path):
    """Per-output placement is impossible without it, so a demo that dropped it
    would not be testing the real window at all."""
    guard, _ = create_guard(tmp_path, demo_mode=True)

    assert guard._config.resolved_overrideredirect() is True


def test_colours_are_gatelocks_defaults_not_overrides(tmp_path: Path):
    """LockConfig's own defaults *are* the unified design system."""
    guard, _ = create_guard(tmp_path)

    assert guard._config.bg == "#211D1B"
    assert guard._config.accent == "#B8862E"
    assert guard._config.on_fill == "#211D1B"


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
    assert guard._decision().balance.available == 0


def test_the_day_after_seeding_gates_normally(tmp_path: Path, hmac_key: Path):
    guard, _ = create_guard(
        tmp_path, probe=probe_of("old-1", "old-2"), key_file=hmac_key, seeded=True
    )

    assert guard._decision().locked


def test_fresh_solves_unlock(tmp_path: Path, hmac_key: Path):
    """The done-condition, end to end: seeded, locked, then new accepted
    submissions release it.

    Two rather than one, because the seeding run settled its own day on credit
    -- that deferral is a loan, so the first solve back pays off Friday and the
    second buys today.
    """
    guard, _ = create_guard(
        tmp_path,
        probe=probe_of("old-1"),
        poll_probe=probe_of("brand-new", "also-new", "old-1"),
        key_file=hmac_key,
        seeded=True,
    )
    assert guard._decision().locked

    guard._on_poll_result(guard._check())

    ledger = load_ledger(tmp_path / "ledger.json", key_file=hmac_key)
    assert ledger.entries["ac:brand-new"].kind == "credit"
    assert ledger.has(f"charge:{MONDAY.isoformat()}")
    assert not guard._decision().locked


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

    guard._on_poll_result(guard._check())

    assert guard._decision().locked
    assert guard._poller.state.consecutive_unverifiable == 1


def test_consecutive_failures_accumulate_then_reset(tmp_path: Path, hmac_key: Path):
    guard, _ = create_guard(
        tmp_path, probe=probe_of(), poll_probe=UNVERIFIABLE, key_file=hmac_key
    )

    guard._on_poll_result(UNVERIFIABLE)
    guard._on_poll_result(UNVERIFIABLE)
    assert guard._poller.state.consecutive_unverifiable == 2

    guard._on_poll_result(probe_of("fresh"))
    assert guard._poller.state.consecutive_unverifiable == 0


def test_a_crashed_poll_counts_as_unverifiable(tmp_path: Path, hmac_key: Path):
    """2026-08-05, defect B: ``_guarded_work`` returns ``None`` whenever
    ``_check`` *raises*, and the old code returned early on it -- skipping both
    ``state.record`` and the repaint. A probe that raises every tick therefore
    left ``consecutive_unverifiable`` at zero for ever, so the blind-time path
    to the hatch never fired and the status line froze at its startup text. A
    crash we cannot see is the one case that most needs to reach the hatch."""
    guard, _ = create_guard(tmp_path, key_file=hmac_key)

    guard._on_poll_result(None)

    assert guard._poller.state.consecutive_unverifiable == 1
    assert "Cannot check LeetCode" in guard._model.status_line


def test_demo_mode_writes_nothing_when_told_not_to(tmp_path: Path, hmac_key: Path):
    guard, _ = create_guard(
        tmp_path,
        probe=probe_of("old"),
        poll_probe=probe_of("new", "old"),
        key_file=hmac_key,
        write_ledger=False,
    )

    guard._on_poll_result(guard._check())

    assert not (tmp_path / "ledger.json").exists()


def test_surfaces_are_registered_and_torn_down(tmp_path: Path):
    guard, _ = create_guard(tmp_path)

    assert guard._frames.names

    for name in list(guard._views):
        guard.teardown_surface(_FakeSurface(name))

    assert guard._views == {}
    assert guard._frames.names == ()


def test_close_is_idempotent(tmp_path: Path):
    guard, _ = create_guard(tmp_path)

    guard.close()
    guard.close()

    assert guard._closed


def test_on_close_stops_the_poller(tmp_path: Path):
    guard, _ = create_guard(tmp_path)

    guard.on_close()

    assert guard._poller._stopped


def test_a_callback_error_is_shown_rather_than_swallowed(tmp_path: Path):
    guard, _ = create_guard(tmp_path)

    guard.on_callback_error()

    for view in guard._views.values():
        view.status_line.configure.assert_called()


def test_focus_ready_tolerates_no_surface(tmp_path: Path):
    """Zero live outputs is 'lock without showing', never 'decline to lock'."""
    guard, _ = create_guard(tmp_path)

    guard.on_focus_ready(None)  # must not raise


def test_the_escape_hatch_settles_the_day_without_spending_credits(
    tmp_path: Path, hmac_key: Path
):
    """An escaped day is forgiven, not free: the balance goes negative."""
    guard, _ = create_guard(tmp_path, probe=probe_of(), key_file=hmac_key, seeded=True)

    guard._on_escape_granted("the network is down and has been all morning")

    ledger = load_ledger(tmp_path / "ledger.json", key_file=hmac_key)
    charge = ledger.entries[f"charge:{MONDAY.isoformat()}"]
    assert charge.detail["source"] == "escape"
    # One escaped day: forgiven, not free.
    assert guard._decision().balance.available == -1


def test_the_hatch_is_offered_from_the_first_second(tmp_path: Path):
    """This assertion used to read ``not ... _should_offer_escape()``, and that
    was the 2026-08-05 incident in one line: for the first ten minutes the lock
    had no exit whatsoever. The budget is what makes the hatch expensive; the
    clock only made it absent when it was needed most."""
    guard, _ = create_guard(tmp_path)

    assert guard._should_offer_escape()


def test_the_hatch_appears_quickly_once_the_gate_goes_blind(tmp_path: Path):
    """Making someone wait out a full offer delay while the gate cannot see
    LeetCode at all would be punishing them for an outage."""
    guard, _ = create_guard(tmp_path, poll_probe=UNVERIFIABLE)
    guard._poller.state.consecutive_unverifiable = 999

    assert guard._should_offer_escape()


def test_the_poll_probe_status_drives_the_status_line(tmp_path: Path, hmac_key: Path):
    guard, _ = create_guard(
        tmp_path, probe=probe_of(), poll_probe=UNVERIFIABLE, key_file=hmac_key
    )

    guard._on_poll_result(UNVERIFIABLE)

    assert "Cannot check LeetCode" in guard._model.status_line
    assert guard._check().status is ProbeStatus.UNVERIFIABLE


class _FakeSurface:
    """Minimal stand-in for gatelock's SurfaceInfo."""

    def __init__(self, output_name: str) -> None:
        self.output_name = output_name
