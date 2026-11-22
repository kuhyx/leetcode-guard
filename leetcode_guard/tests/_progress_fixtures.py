"""Shared builders for the progress-row tests (current-era prices)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from leetcode_guard._balance import Balance
from leetcode_guard._debt import NO_DEBT
from leetcode_guard._gate import DayContext, GateDecision, decide
from leetcode_guard._gate_progress import apply_progress
from leetcode_guard._gate_state import GateState
from leetcode_guard._ledger_entries import progress_entry
from leetcode_guard._ledger_io import Ledger, append
from leetcode_guard.tests._ledger_fixtures import (
    add_charge,
    credits_for,
    ledger_with_credits,
)

# Current-era prices (2026-10-07): Mon/Fri 3, Tue-Thu 2, Sat/Sun 4. The shared
# fixture week is in an older era where a weekday costs 1.
MONDAY = date(2026, 11, 23)
TUESDAY = date(2026, 11, 24)
FRIDAY = date(2026, 11, 20)
SATURDAY = date(2026, 11, 28)
NOW = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
FAR_DAY = date(2099, 1, 1)

if TYPE_CHECKING:
    from pathlib import Path


def decision_of(ledger: Ledger, key: Path, *, day=MONDAY, **flags) -> GateDecision:
    """The gate's real verdict for ``day`` over ``ledger``."""
    context = DayContext(**flags)
    return decide(ledger, day=day, now=NOW, key_file=key, context=context)


def shaped(*, earned: int, available: int, needed: int, key: Path) -> tuple:
    """A ledger and decision with exactly these three numbers.

    ``earned`` credits today (Monday); the rest of ``available`` is made by a
    charge for Friday (negative) or banked credits dated Friday (positive).
    """
    ledger = ledger_with_credits(earned, day=MONDAY, key_file=key)
    gap = available - earned
    if gap > 0:
        banked = credits_for(gap, day=FRIDAY, now=NOW, key_file=key)
        append(ledger, [replace(e, entry_id=f"b-{e.entry_id}") for e in banked])
    balance = Balance(
        credits=max(available, earned),
        charged=0,
        available=available,
        discounted=0,
        tampered=0,
        integrity_ok=True,
        unparsable=0,
    )
    decision = GateDecision(
        state=GateState.LOCKED_INSUFFICIENT,
        day=MONDAY,
        cost=available + needed,
        balance=balance,
        debt=NO_DEBT,
        needed=needed,
        charge=None,
        reason="test",
    )
    return ledger, decision


def ledgers(key: Path) -> list[Ledger]:
    """Several shapes: empty, credits, banked, charged, a past charge."""
    charged = ledger_with_credits(3, day=MONDAY, key_file=key)
    add_charge(charged, MONDAY, key_file=key)
    past = ledger_with_credits(2, day=FRIDAY, key_file=key)
    add_charge(past, FRIDAY, key_file=key)
    return [
        Ledger(),
        ledger_with_credits(1, day=MONDAY, key_file=key),
        ledger_with_credits(2, day=FRIDAY, key_file=key),
        ledger_with_credits(4, day=MONDAY, key_file=key),
        charged,
        past,
    ]


def with_progress(ledger: Ledger, key: Path) -> Ledger:
    """A copy carrying progress rows: honest, a future-dated one, a forged one."""
    clone = Ledger(entries=dict(ledger.entries))
    rows = [
        progress_entry(for_day=MONDAY, done=1, target=3, now=NOW, key_file=key),
        progress_entry(for_day=MONDAY, done=2, target=3, now=NOW, key_file=key),
        progress_entry(for_day=FAR_DAY, done=1, target=3, now=NOW, key_file=key),
        replace(
            progress_entry(for_day=MONDAY, done=9, target=9, now=NOW, key_file=key),
            entry_id="progress:2026-11-23:9:9",
            amount=999,
            signature=None,
            verified=False,
        ),
    ]
    append(clone, rows)
    return clone


def never_free(_day: date) -> bool:
    """No day is in the free-day pool."""
    return False


def sign_progress(ledger: Ledger, decision: GateDecision, key: Path) -> bool:
    """``apply_progress`` for ``decision`` at ``NOW``, into ``key``'s folder."""
    return apply_progress(
        ledger, decision, key.parent / "ledger.json", now=NOW, key_file=key
    )
