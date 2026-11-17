"""The evening lock window: credit watch, the way out, and no other way out."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from gatelock import log_integrity
import pytest

from leetcode_guard import _evening
from leetcode_guard import _glyphs as g
from leetcode_guard._constants import RANK_LEETCODE_GUARD
from leetcode_guard._daycost import local_today
from leetcode_guard._ledger import SOURCE_ESCAPE
from leetcode_guard._ledger_entries import charge_entry
from leetcode_guard._ledger_io import append, load_ledger, save_ledger
from leetcode_guard._lock_poll import _UNLOCK_LINGER_MS
from leetcode_guard.tests._guard_factories import create_guard, probe_of
from leetcode_guard.tests._ledger_fixtures import add_charge

if TYPE_CHECKING:
    from pathlib import Path

CREDIT_POLL_MS = 3_000


def _now() -> datetime:
    return datetime.now().astimezone()


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch, hmac_key: Path) -> None:
    monkeypatch.setattr(log_integrity, "DEFAULT_HMAC_KEY_FILE", hmac_key)


def _guard(tmp_path: Path, hmac_key: Path, *, evening: bool = True):
    guard, _ = create_guard(
        tmp_path,
        evening=evening,
        now=_now(),
        demo_mode=False,
        seeded=True,
        key_file=hmac_key,
        probe=probe_of("old-1"),
    )
    return guard


def _afters(guard) -> list[tuple]:
    return [c.args for c in guard.root.after.call_args_list]


def _credit_tick(guard):
    ticks = [a[1] for a in _afters(guard) if a[0] == CREDIT_POLL_MS]
    assert len(ticks) == 1, "the evening window arms exactly one credit watch"
    return ticks[0]


def _pay(tmp_path: Path, hmac_key: Path, *, source: str | None = None) -> None:
    ledger = load_ledger(tmp_path / "ledger.json", key_file=hmac_key)
    if source is None:
        add_charge(ledger, local_today(), key_file=hmac_key, now=_now())
    else:
        append(
            ledger,
            [charge_entry(local_today(), now=_now(), source=source, key_file=hmac_key)],
        )
    save_ledger(tmp_path / "ledger.json", ledger)


def test_a_charge_row_landing_while_the_window_is_up_closes_it(
    tmp_path: Path, hmac_key: Path
) -> None:
    """Credit watch: the leetcode charge lands, the window takes itself down."""
    guard = _guard(tmp_path, hmac_key)
    tick = _credit_tick(guard)
    tick()
    assert (_UNLOCK_LINGER_MS, guard.close) not in _afters(guard)

    _pay(tmp_path, hmac_key)
    tick()

    assert (_UNLOCK_LINGER_MS, guard.close) in _afters(guard)
    guard.close()
    assert guard.exit_code == 0


def test_an_escape_charge_does_not_pay_the_rung(tmp_path: Path, hmac_key: Path) -> None:
    """Only source=leetcode pays; the window stays up (fail closed)."""
    guard = _guard(tmp_path, hmac_key)
    tick = _credit_tick(guard)
    _pay(tmp_path, hmac_key, source=SOURCE_ESCAPE)

    tick()

    assert (_UNLOCK_LINGER_MS, guard.close) not in _afters(guard)


def test_a_poll_that_calls_the_day_settled_does_not_lift_an_unpaid_rung(
    tmp_path: Path, hmac_key: Path
) -> None:
    """decide() says "already charged" for an escaped day; the chain would loop."""
    guard = _guard(tmp_path, hmac_key)
    _pay(tmp_path, hmac_key, source=SOURCE_ESCAPE)
    guard.ledger = load_ledger(tmp_path / "ledger.json", key_file=hmac_key)
    assert not guard.decision().locked

    guard.on_poll_result(probe_of("old-1"))

    assert (_UNLOCK_LINGER_MS, guard.close) not in _afters(guard)
    assert not guard.run_state.closed


def test_a_paid_poll_releases_normally(tmp_path: Path, hmac_key: Path) -> None:
    """The guard's own poll writes the charge, then the release goes through."""
    guard = _guard(tmp_path, hmac_key)
    _pay(tmp_path, hmac_key)
    guard.ledger = load_ledger(tmp_path / "ledger.json", key_file=hmac_key)

    guard.on_poll_result(probe_of("old-1"))

    assert (_UNLOCK_LINGER_MS, guard.close) in _afters(guard)


def test_end_evening_closes_with_exit_ten(tmp_path: Path, hmac_key: Path) -> None:
    """The control is the one way out that is not a credit."""
    guard = _guard(tmp_path, hmac_key)

    guard.end_evening()

    assert guard.run_state.closed
    assert guard.exit_code == 10
    assert guard.exit_code == _evening.EXIT_END_EVENING


def test_the_end_evening_button_is_on_every_surface_from_t0(
    tmp_path: Path, hmac_key: Path, tk_mock
) -> None:
    """Built with the surface, wired to end_evening, glyph only."""
    guard = _guard(tmp_path, hmac_key)
    tk_mock.Button.reset_mock()

    guard.build_surface(tk_mock.Frame(), MagicMock(output_name="DP-0"))

    buttons = [c.kwargs for c in tk_mock.Button.call_args_list]
    ending = [b for b in buttons if b.get("text") == g.END_EVENING]
    assert len(ending) == 1
    assert not any(ch.isalpha() and ch.isascii() for ch in ending[0]["text"])

    ending[0]["command"]()

    assert guard.exit_code == _evening.EXIT_END_EVENING


def test_an_ordinary_lock_has_no_end_evening_button(
    tmp_path: Path, hmac_key: Path, tk_mock
) -> None:
    """The control exists only in evening mode."""
    guard = _guard(tmp_path, hmac_key, evening=False)
    tk_mock.Button.reset_mock()

    guard.build_surface(tk_mock.Frame(), MagicMock(output_name="DP-0"))

    assert all(
        c.kwargs.get("text") != g.END_EVENING for c in tk_mock.Button.call_args_list
    )
    assert CREDIT_POLL_MS not in [a[0] for a in _afters(guard)]


def test_evening_has_no_carrot_watch_and_no_escape_hatch(
    tmp_path: Path, hmac_key: Path
) -> None:
    """The morning-session poll is off, and the hatch settles with a non-paying
    charge, so it is withheld: end-evening is the way out."""
    guard = _guard(tmp_path, hmac_key)

    assert guard.carrot_job is None
    assert guard.should_offer_escape() is False


def test_the_evening_lock_ranks_150(tmp_path: Path, hmac_key: Path) -> None:
    """Below screen-locker (200), per the contract."""
    guard = _guard(tmp_path, hmac_key)

    assert guard.run_state.config.rank == RANK_LEETCODE_GUARD == 150
