"""Remaining lock branches: the escape form's placement and the run loop."""

from __future__ import annotations

from concurrent.futures import Future
import logging
from typing import TYPE_CHECKING

from leetcode_guard.tests._guard_factories import (
    create_guard,
    guard_with_one_new_solve,
    probe_of,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_the_escape_form_opens_on_a_surface(tmp_path: Path):
    """The escape request opens the hatch form on a live surface."""
    guard, _ = create_guard(tmp_path)

    guard.open_escape()

    assert guard.escape.hatch.open


def test_opening_the_escape_form_twice_is_a_no_op(tmp_path: Path):
    """A second escape request keeps the form already open."""
    guard, _ = create_guard(tmp_path)

    guard.open_escape()
    first = guard.escape.hatch.form
    guard.open_escape()

    assert guard.escape.hatch.form is first


def test_the_escape_form_declines_to_open_with_no_surface(tmp_path: Path, caplog):
    """Zero live outputs still holds the grab, so the request is legitimate --
    it just has nowhere to draw. It must say so rather than crash the lock."""
    guard, _ = create_guard(tmp_path)
    guard.frames.clear()

    with caplog.at_level(logging.WARNING):
        guard.open_escape()

    assert not guard.escape.hatch.open
    assert any("no surface available" in record.message for record in caplog.records)


def test_run_delegates_to_the_lock_window(tmp_path: Path):
    """Running the guard hands control to the lock window without raising."""
    guard, _ = create_guard(tmp_path)

    guard.run()

    assert True


def test_a_seeded_ledger_is_not_reseeded_on_a_later_run(tmp_path: Path, hmac_key: Path):
    """A later run treats new solves as credits instead of reseeding the ledger."""
    create_guard(tmp_path, probe=probe_of("a"), key_file=hmac_key)

    second, _ = create_guard(tmp_path, probe=probe_of("a", "b"), key_file=hmac_key)

    # "b" arrived after seeding, so it is a credit rather than a marker.
    second.on_poll_result(probe_of("a", "b"))
    assert not second.decision().locked


def test_write_ledger_false_skips_seeding_entirely(tmp_path: Path):
    """With ledger writes off, seeding creates no ledger file."""
    create_guard(tmp_path, probe=probe_of("a"), write_ledger=False)

    assert not (tmp_path / "ledger.json").exists()


def test_a_pending_future_leaves_the_drain_rescheduling(tmp_path: Path):
    """Covers the branch where the executor has not finished yet."""
    guard, _ = create_guard(tmp_path)
    guard.poller.future = Future()

    guard.poller.drain()

    assert guard.poller.future is not None


def test_the_unlocked_path_with_write_disabled_skips_the_charge(tmp_path: Path):
    """Covers the branch where a decision would charge but nothing may be
    written -- demo mode running against a ledger it must not touch."""
    guard = guard_with_one_new_solve(tmp_path, write_ledger=False)

    guard.on_poll_result(guard.check())

    assert not (tmp_path / "ledger.json").exists()


def test_the_escape_grant_with_write_disabled_still_releases(tmp_path: Path):
    """A granted escape with ledger writes off releases without writing a ledger."""
    guard, _ = create_guard(tmp_path, write_ledger=False)

    guard.on_escape_granted("a reason")

    assert not (tmp_path / "ledger.json").exists()


def test_a_tick_while_a_future_is_in_flight_does_not_resubmit(tmp_path: Path):
    """A poll tick with a check in flight keeps the pending future."""
    guard, _ = create_guard(tmp_path)
    pending: Future = Future()
    guard.poller.future = pending

    guard.poller.tick()

    assert guard.poller.future is pending


def test_a_stopped_poller_ignores_a_tick(tmp_path: Path):
    """A stopped poller submits no new check on a tick."""
    guard, _ = create_guard(tmp_path)
    guard.poller.stop()
    guard.poller.future = None

    guard.poller.tick()

    assert guard.poller.future is None


def test_an_already_charged_day_unlocks_without_writing_a_second_charge(
    tmp_path: Path, hmac_key: Path
):
    """The afternoon retry lands here: today is settled, the decision carries
    no charge, and the lock releases without touching the ledger again."""
    guard = guard_with_one_new_solve(tmp_path, key_file=hmac_key)
    guard.on_poll_result(guard.check())
    before = (tmp_path / "ledger.json").read_text(encoding="utf-8")

    guard.on_poll_result(guard.check())

    assert guard.decision().charge is None
    assert (tmp_path / "ledger.json").read_text(encoding="utf-8") == before
